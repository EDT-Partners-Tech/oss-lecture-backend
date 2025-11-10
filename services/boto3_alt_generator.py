# © [2025] EDT&Partners. Licensed under CC BY 4.0.

#!/usr/bin/env python3
"""
Generator of alt text using boto3 directly to AWS Bedrock with parallelism
"""

import base64
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional
import json
import boto3
from botocore.exceptions import ClientError
from utility.aws_clients import get_caller_identity
from function.llms.bedrock_invoke import get_model_region, get_model_by_id, is_inference_model
from config.epub_config import epub_config
# Removed icecream import to avoid AST recursion issues
from utils.epub.images.context_extractor import format_context_for_ai_simple

logger = logging.getLogger(__name__)


class Boto3AltGenerator:
    """
    Generador de alt text usando boto3 directo a AWS Bedrock con procesamiento paralelo
    """

    def __init__(self, max_workers: int = 10, max_retries: int = 3, locale: str = "es", audience_profile: str = ""):
        """
        Inicializa el generador con configuración de paralelismo y reintentos
        
        Args:
            max_workers: Número máximo de threads paralelos
            max_retries: Número máximo de reintentos por imagen
            locale: Código de idioma para generar alt text (ej: "es", "en", "fr"). Default: "es"
            audience_profile: Perfil de la audiencia objetivo para adaptar el lenguaje. Default: ""
        """
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.locale = locale
        self.audience_profile = audience_profile
        self.model_id = "anthropic.claude-3-7-sonnet-20250219-v1:0"
        self.region = epub_config.S3_REGION
        self.bedrock_client = None
        
        # Configuración de AWS
        self._initialize_aws_client()
        
        # Get prompts in the specified language
        self.prompts = self._get_prompts_for_locale(locale)
        
        # System prompt configuration using the specified language
        self.system_prompt = self.prompts["system_prompt"]
        
        # If there's an audience profile, add it to the system prompt
        if self.audience_profile:
            self.system_prompt += f"\n\n🎯 TARGET AUDIENCE: {self.audience_profile}\nAdapt the language, complexity, and vocabulary to be appropriate for this specific audience."

    def _get_prompts_for_locale(self, locale: str) -> Dict[str, str]:
        """
        Retorna los prompts completos en el idioma especificado desde archivos JSON
        
        Args:
            locale: Código de idioma
            
        Returns:
            Diccionario con system_prompt, alt_prompt_template y long_desc_prompt_template
        """
        locale_lower = locale.lower()
        
        # Path to prompts directory
        prompts_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            "config", "prompts", "epub"
        )
        
        # Path to the requested language file
        locale_file = os.path.join(prompts_dir, f"{locale_lower}.json")
        
        # Try to load the requested language file
        if os.path.exists(locale_file):
            try:
                with open(locale_file, 'r', encoding='utf-8') as f:
                    prompts = json.load(f)
                print(f"✅ Prompts cargados para idioma: {prompts.get('language_name', locale_lower)}")
                return prompts
            except Exception as e:
                print(f"⚠️ Error leyendo archivo de prompts '{locale_file}': {str(e)}")
                print(f"   Trying to load Spanish as default...")
        else:
            print(f"⚠️ Archivo de prompts '{locale_file}' no encontrado")
            print(f"   Idiomas disponibles: {self._get_available_locales(prompts_dir)}")
            print(f"   Using Spanish as default...")
        
        # Fallback: try to load Spanish
        es_file = os.path.join(prompts_dir, "es.json")
        if os.path.exists(es_file):
            try:
                with open(es_file, 'r', encoding='utf-8') as f:
                    prompts = json.load(f)
                print(f"✅ Spanish prompts loaded as fallback")
                return prompts
            except Exception as e:
                print(f"❌ Critical error: could not load Spanish: {str(e)}")
        
        # Last fallback: hardcoded Spanish prompts
        print(f"⚠️ Using hardcoded prompts as last resort")
        return self._get_hardcoded_spanish_prompts()
    
    def _get_available_locales(self, prompts_dir: str) -> list:
        """
        Retorna lista de idiomas disponibles
        
        Args:
            prompts_dir: Directorio de prompts
            
        Returns:
            Lista de códigos de idioma disponibles
        """
        try:
            if not os.path.exists(prompts_dir):
                return []
            
            available = []
            for file in os.listdir(prompts_dir):
                if file.endswith('.json'):
                    available.append(file.replace('.json', ''))
            return available
        except Exception:
            return []
    
    def _get_hardcoded_spanish_prompts(self) -> Dict[str, str]:
        """
        Returns hardcoded Spanish prompts as last fallback
        
        Returns:
            Dictionary with Spanish prompts
        """
        return {
            "locale": "es",
            "language_name": "Spanish (hardcoded fallback)",
            "system_prompt": """
Eres un especialista en accesibilidad web. Tu objetivo es ayudar a personas ciegas a comprender las imágenes en su contexto real dentro de la página.

ENTREGABLES:
1) ALT: texto alternativo breve (≤125 caracteres), claro y fiel a lo visible.
2) DESCRIPCIÓN LARGA (< 500 caracteres): relación de la imagen con el CONTEXTO HTML.

FORMATO DE SALIDA (JSON mínimo):
{
  "alt": "...",
  "needs_long_desc": true|false,
  "long_desc": "..."
}
            """,
            "alt_prompt_template": "Analiza la imagen y devuelve JSON con alt text (≤125 caracteres), needs_long_desc (boolean), y long_desc (si aplica).\n\nCONTEXTO: {context}\nArchivo: {filename}",
            "long_desc_prompt_template": "Genera una descripción larga detallada para esta imagen.\n\nCONTEXTO: {context}"
        }
    
    def _initialize_aws_client(self) -> None:
        """Inicializa el cliente de AWS Bedrock"""
        try:
            # Usar el cliente AWS del proyecto actual
            from utility.aws_clients import bedrock_runtime_client
            self.bedrock_client = bedrock_runtime_client
            
            print(f"✅ Cliente Boto3 Bedrock inicializado")
            
        except Exception as e:
            logger.error(f"Error inicializando cliente Bedrock: {str(e)}")
            # Fallback: crear cliente directo
            try:
                self.bedrock_client = boto3.client(
                    'bedrock-runtime',
                    region_name=self.region
                )
                print(f"✅ Cliente Boto3 Bedrock inicializado (fallback)")
            except Exception as fallback_e:
                logger.error(f"Error en fallback Bedrock: {str(fallback_e)}")
                raise Exception(f"No se pudo inicializar Bedrock: {str(e)}")

    def _encode_image_to_base64(self, image_path: str) -> Optional[str]:
        """
        Convierte imagen a base64 para envío a Bedrock
        
        Args:
            image_path: Ruta de la imagen
            
        Returns:
            String base64 o None si hay error
        """
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error codificando imagen {image_path}: {str(e)}")
            return None

    def _get_image_media_type(self, image_path: str) -> str:
        """
        Determina el tipo de media de la imagen
        
        Args:
            image_path: Ruta de la imagen
            
        Returns:
            Tipo de media (image/jpeg, image/png, etc.)
        """
        ext = os.path.splitext(image_path)[1].lower()
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp'
        }
        return media_types.get(ext, 'image/jpeg')

    def _clean_alt_text_response(self, alt_text: str) -> str:
        """
        Limpia el texto alternativo de prefijos innecesarios
        
        Args:
            alt_text: Texto alternativo crudo
            
        Returns:
            Texto alternativo limpio
        """
        if not alt_text:
            return ""
        
        # Remover prefijos comunes
        prefixes_to_remove = [
            "imagen de", "foto de", "imagen que muestra", "fotografía de",
            "imagen:", "foto:", "imagen que", "foto que", "una imagen de",
            "una foto de", "la imagen muestra", "la foto muestra"
        ]
        
        cleaned = alt_text.strip()
        for prefix in prefixes_to_remove:
            if cleaned.lower().startswith(prefix.lower()):
                cleaned = cleaned[len(prefix):].strip()
                break
        
        # Limitar a 125 caracteres
        if len(cleaned) > 125:
            cleaned = cleaned[:122] + "..."
        
        return cleaned

    def _check_image_size(self, image_path: str) -> bool:
        """Verifica si la imagen supera el umbral de tamaño"""
        try:
            size_bytes = os.path.getsize(image_path)
            return size_bytes >= 80 * 1024  # 80KB
        except Exception:
            return False

    def _check_if_needs_long_description(self, image_filename: str, context: str, size_over_threshold: bool) -> bool:
        """Determina si la imagen necesita descripción larga"""
        keywords = ["chart", "graph", "diagram", "map", "table", "formula", "code", "infographic"]
        name = image_filename.lower()
        ctx_l = context.lower()
        heuristic_match = any(k in name for k in keywords) or any(k in ctx_l for k in keywords)
        
        if heuristic_match:
            print(f"🧭 {image_filename}: heurística de complejidad activada por nombre/contexto")
        if size_over_threshold:
            print(f"🧱 {image_filename}: activado por tamaño ≥ 80KB")
            
        return heuristic_match or size_over_threshold

    def _parse_model_response(self, response, needs_long_by_heuristic: bool, image_filename: str) -> Optional[Dict]:
        """Parsea la respuesta del modelo AI"""
        try:
            response_data = json.loads(response['body'].read())
            
            if 'content' not in response_data or not response_data['content']:
                return None
                
            raw_text = response_data['content'][0]['text'].strip()
            
            # Intentar parsear JSON directamente
            try:
                return json.loads(raw_text)
            except Exception:
                # Sanitizar: quitar code fences y extraer primer objeto JSON
                sanitized = raw_text.strip()
                if sanitized.startswith("```"):
                    sanitized = sanitized.strip('`')
                    if sanitized.lower().startswith("json"):
                        sanitized = sanitized[4:].lstrip()
                
                # Extraer el primer bloque { ... }
                try:
                    import re
                    match = re.search(r"\{[\s\S]*\}", sanitized)
                    if match:
                        candidate = match.group(0)
                        return json.loads(candidate)
                except Exception:
                    pass
                
                # Último intento: extraer alt simple
                try:
                    import re
                    m = re.search(r'"alt"\s*:\s*"([^"]+)"', sanitized)
                    if m:
                        cleaned_alt = self._clean_alt_text_response(m.group(1))
                        return {
                            "alt": cleaned_alt,
                            "needs_long_desc": needs_long_by_heuristic,
                            "long_desc": ""
                        }
                except Exception:
                    pass
                    
            return None
            
        except Exception as e:
            print(f"⚠️ {image_filename}: Error parseando respuesta: {str(e)}")
            return None

    def _generate_fallback_alt(self, image_filename: str, context: str) -> str:
        """
        Genera un alt text genérico como fallback
        
        Args:
            image_filename: Nombre del archivo de imagen
            context: Contexto de la imagen
            
        Returns:
            Alt text genérico
        """
        # Extraer información básica del nombre del archivo
        name_without_ext = os.path.splitext(image_filename)[0]
        
        # Palabras clave comunes en nombres de archivos
        if any(word in name_without_ext.lower() for word in ['chart', 'graph', 'diagram', 'chart']):
            return "Gráfico o diagrama"
        elif any(word in name_without_ext.lower() for word in ['table', 'tabla']):
            return "Tabla de datos"
        elif any(word in name_without_ext.lower() for word in ['map', 'mapa']):
            return "Mapa"
        elif any(word in name_without_ext.lower() for word in ['icon', 'icono']):
            return "Icono"
        else:
            return f"Imagen relacionada con {context[:50]}"

    def _generate_alt_text_single(self, image_path: str, context: str) -> Dict[str, Any]:
        """
        Genera alt text para una imagen individual
        
        Args:
            image_path: Ruta de la imagen
            context: Contexto de la imagen
            
        Returns:
            Dict con el resultado de la generación
        """
        image_filename = os.path.basename(image_path)
        
        # Codificar imagen a base64
        base64_image = self._encode_image_to_base64(image_path)
        if not base64_image:
            return {
                "success": False,
                "alt_text": "",
                "error": "No se pudo codificar la imagen",
                "attempts": 0
            }
        
        # Check image size
        size_over_threshold = self._check_image_size(image_path)
        needs_long_by_heuristic = self._check_if_needs_long_description(image_filename, context, size_over_threshold)
        
        # Try to generate alt text with retries
        for attempt in range(1, self.max_retries + 1):
            try:
                # Prepare message for Claude using the language template
                prompt_text = self.prompts["alt_prompt_template"].format(
                    context=context,
                    filename=image_filename,
                    audience_profile=self.audience_profile if self.audience_profile else "público general"
                )
                
                messages = [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt_text
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": self._get_image_media_type(image_path),
                                    "data": base64_image
                                }
                            }
                        ]
                    }
                ]
                
                # Invocar modelo
                body = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 100,
                    "system": self.system_prompt,
                    "messages": messages,
                    "temperature": 0.0
                }

                # print(f"model_arn: {model_id}")
                account_id = get_caller_identity()
                region, suffix = get_model_region(self.model_id)
                model = get_model_by_id(self.model_id)
                
                if not model:
                    raise ValueError(f"Model not found for ID: {self.model_id}")


                if is_inference_model(self.model_id):
                    model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{self.model_id}"
                else:
                    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{self.model_id}"

                print(f"🔧 Model ARN: {model_arn}")
                
                response = self.bedrock_client.invoke_model(
                    modelId=model_arn,
                    body=json.dumps(body),
                    contentType="application/json"
                )
                
                # Procesar respuesta
                parsed = self._parse_model_response(response, needs_long_by_heuristic, image_filename)
                
                if parsed and isinstance(parsed, dict) and "alt" in parsed:
                    alt_text = self._clean_alt_text_response(parsed["alt"])
                    
                    if alt_text:
                        return {
                            "success": True,
                            "alt_text": alt_text,
                            "needs_long_desc": parsed.get("needs_long_desc", False),
                            "long_desc": parsed.get("long_desc", ""),
                            "attempts": attempt
                        }
                    else:
                        print(f"⚠️ {image_filename}: Alt vacío en intento {attempt}")
                else:
                    print(f"⚠️ {image_filename}: Respuesta inválida en intento {attempt}")
                    
            except Exception as e:
                print(f"⚠️ {image_filename}: Error en intento {attempt}: {str(e)}")
                if attempt == self.max_retries:
                    # Último intento fallido, usar fallback
                    fallback_alt = self._generate_fallback_alt(image_filename, context)
                    return {
                        "success": True,
                        "alt_text": fallback_alt,
                        "needs_long_desc": False,
                        "long_desc": "",
                        "attempts": attempt,
                        "fallback": True
                    }
        
        # Si llegamos aquí, todos los intentos fallaron
        fallback_alt = self._generate_fallback_alt(image_filename, context)
        return {
            "success": True,
            "alt_text": fallback_alt,
            "needs_long_desc": False,
            "long_desc": "",
            "attempts": self.max_retries,
            "fallback": True
        }

    
    def process_long_descriptions_for_large_images(self, webpage_dir: str, min_kb: int = 80) -> Dict[str, Any]:
        """
        Genera descripciones largas para imágenes cuyo tamaño en disco sea ≥ min_kb.
        - Busca imágenes en subcarpetas que contengan 'image'
        - Crea images_tags/detail_<NOMBRE-CON-EXT>.txt
        """
        # Check if we're in development mode
        if epub_config.IS_DEVELOPMENT:
            print("🧪 Modo desarrollo activado (ENVIRONMENT=development):")
            print("   📝 Usando texto fijo para descripciones largas")
            print("   💰 Evitando costos de boto3")
            return self._process_development_long_descriptions(webpage_dir, min_kb)
        
        print(f"🧱 Iniciando generación de descripciones largas para imágenes ≥ {min_kb}KB (paralelo: {self.max_workers})")
        
        # Collect all candidate images
        large_images = []
        for root, dirs, files in os.walk(webpage_dir):
            if "image" in os.path.basename(root).lower():
                for fname in files:
                    if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                        continue
                    img_path = os.path.join(root, fname)
                    try:
                        size_bytes = os.path.getsize(img_path)
                        if size_bytes >= min_kb * 1024:
                            large_images.append((img_path, fname))
                    except Exception:
                        continue

        if not large_images:
            return {"success": True, "processed": 0, "created": 0, "skipped": 0, "message": "Sin imágenes grandes encontradas"}

        images_tags_dir = os.path.join(webpage_dir, "images_tags")
        os.makedirs(images_tags_dir, exist_ok=True)

        # Función para procesar una imagen individual
        def process_single_large_image(image_data: tuple) -> dict:
            img_path, fname = image_data
            base_name = os.path.splitext(fname)[0]
            detail_path = os.path.join(images_tags_dir, f"detail_{base_name}.txt")
            
            # Si ya existe, no sobrescribir
            if os.path.exists(detail_path):
                return {"status": "skipped", "filename": fname, "reason": "detail existente"}
            
            try:
                # Extraer contexto enriquecido
                enriched_context = ""
                try:
                    enriched_context = format_context_for_ai_simple(img_path, webpage_dir)
                except Exception:
                    pass

                # Generar solo long desc
                long_desc = self._generate_only_long_desc(img_path, enriched_context)
                if not long_desc or not long_desc.strip():
                    long_desc = (enriched_context or "").strip()[:1200]
                    print(f"ℹ️ {fname}: usando contexto como long desc (fallback ≥ {min_kb}KB)")

                # Guardar archivo
                with open(detail_path, "w", encoding="utf-8") as df:
                    df.write(long_desc.strip())
                
                return {
                    "status": "created", 
                    "filename": fname, 
                    "chars": len(long_desc.strip()),
                    "path": detail_path
                }
                
            except Exception as e:
                return {
                    "status": "error", 
                    "filename": fname, 
                    "error": str(e)
                }

        # Procesar en paralelo
        processed = 0
        created = 0
        skipped = 0
        errors = 0

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Send all tasks
            futures = {executor.submit(process_single_large_image, img_data): img_data for img_data in large_images}
            
            # Collect results as they complete
            for future in as_completed(futures):
                result = future.result()
                processed += 1
                
                if result["status"] == "created":
                    created += 1
                    print(f"📝 {result['filename']}: detail creado ({result['chars']} chars)")
                elif result["status"] == "skipped":
                    skipped += 1
                    print(f"⏭️ {result['filename']}: detail existente, saltando")
                elif result["status"] == "error":
                    errors += 1
                    print(f"❌ Error creando detail para {result['filename']}: {result['error']}")

        print(f"📊 Resumen descripciones largas: {processed} procesadas, {created} creadas, {skipped} saltadas, {errors} errores")
        
        return {
            "success": errors == 0, 
            "processed": processed, 
            "created": created, 
            "skipped": skipped, 
            "errors": errors
        }

    def _process_development_long_descriptions(self, webpage_dir: str, min_kb: int = 80) -> Dict[str, Any]:
        """
        Procesa descripciones largas en modo desarrollo usando texto fijo para evitar costos de boto3.
        
        Args:
            webpage_dir: Directorio base de webpage
            min_kb: Tamaño mínimo en KB (se ignora en modo desarrollo)
            
        Returns:
            Diccionario con resultados del procesamiento
        """
        print("🧪 Procesando descripciones largas en modo desarrollo...")
        
        images_dir_list: List[str] = []
        for root, dirs, files in os.walk(webpage_dir):
            if "image" in os.path.basename(root).lower():
                images_dir_list.append(root)

        if not images_dir_list:
            return {"success": True, "processed": 0, "created": 0, "skipped": 0, "message": "Sin carpetas de imágenes"}

        images_tags_dir = os.path.join(webpage_dir, "images_tags")
        os.makedirs(images_tags_dir, exist_ok=True)

        processed = 0
        created = 0
        skipped = 0

        for img_dir in images_dir_list:
            for fname in os.listdir(img_dir):
                if not fname.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    continue
                    
                processed += 1
                
                base_name = os.path.splitext(fname)[0]
                detail_path = os.path.join(images_tags_dir, f"detail_{base_name}.txt")
                
                # Si ya existe, no sobrescribir por ahora
                if os.path.exists(detail_path):
                    print(f"⏭️ {fname}: detail existente, saltando")
                    skipped += 1
                    continue

                try:
                    # Escribir texto fijo de desarrollo
                    with open(detail_path, "w", encoding="utf-8") as df:
                        df.write(epub_config.DEV_ARIA_DETAILS)
                    created += 1
                    print(f"📝 {base_name}: detail creado (modo desarrollo) - '{epub_config.DEV_ARIA_DETAILS}'")
                except Exception as e:
                    print(f"❌ Error creando detail para {base_name}: {str(e)}")

        print("📊 Resumen modo desarrollo:")
        print(f"   - Imágenes procesadas: {processed}")
        print(f"   - Archivos creados: {created}")
        print(f"   - Archivos saltados: {skipped}")
        print(f"   - Texto usado: '{epub_config.DEV_ARIA_DETAILS}'")

        return {
            "success": True, 
            "processed": processed, 
            "created": created, 
            "skipped": skipped,
            "dev_mode": True,
            "dev_text": epub_config.DEV_ARIA_DETAILS
        }

    def _generate_only_long_desc(self, image_path: str, context: str = "") -> str:
        """
        Genera únicamente la descripción larga usando el mismo modelo, sin límite de longitud.
        """
        base64_image = self._encode_image_to_base64(image_path)
        if not base64_image:
            return ""

        account_id = get_caller_identity()
        region, suffix = get_model_region(self.model_id)
        model = get_model_by_id(self.model_id)
        
        if not model:
            raise ValueError(f"Model not found for ID: {self.model_id}")


        if is_inference_model(self.model_id):
            model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{self.model_id}"
        else:
            model_arn = f"arn:aws:bedrock:{region}::foundation-model/{self.model_id}"

        print(f"🔧 Model ARN: {model_arn}")
        
        # Usar el template de descripción larga del idioma
        prompt_text = self.prompts["long_desc_prompt_template"].format(
            context=context,
            audience_profile=self.audience_profile if self.audience_profile else "público general"
        )
        
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt_text,
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": self._get_image_media_type(image_path),
                            "data": base64_image,
                        },
                    },
                ],
            }
        ]

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "system": self.system_prompt,
            "messages": messages,
            "temperature": 0.0,
        }

        try:
            response = self.bedrock_client.invoke_model(
                modelId=model_arn,
                body=json.dumps(body),
                contentType="application/json",
            )
            response_data = json.loads(response["body"].read())
            if "content" in response_data and response_data["content"]:
                long_desc = response_data["content"][0]["text"].strip()
                return long_desc
        except Exception:
            return ""

        return ""

    def process_images_parallel(
        self, 
        image_paths: List[str], 
        output_dir: str, 
        context: str = "educational content"
    ) -> Dict[str, Any]:
        """
        Procesa múltiples imágenes en paralelo
        
        Args:
            image_paths: Lista de rutas de imágenes
            output_dir: Directorio de salida para archivos tag_
            context: Contexto base para las imágenes
            
        Returns:
            Dict con estadísticas del procesamiento
        """
        print(f"🚀 Procesando {len(image_paths)} imágenes con Boto3 (paralelo: {self.max_workers})")
        
        # Crear directorio de salida
        os.makedirs(output_dir, exist_ok=True)
        
        results = {}
        successful_generations = 0
        failed_generations = 0
        decorative_elements = 0
        long_desc_created = 0
        fallback_used = 0
        
        # Función para procesar imagen individual con contexto
        def process_single_image(image_path: str) -> tuple:
            try:
                # Extraer contexto enriquecido si disponible
                enriched_context = context
                try:
                    # Intentar extraer contexto del directorio padre
                    webpage_dir = os.path.dirname(os.path.dirname(output_dir))
                    # Aquí podrías agregar lógica de extracción de contexto si es necesario
                except:
                    pass  # Usar contexto básico si falla la extracción
                
                result = self._generate_alt_text_single(image_path, enriched_context)
                return (image_path, result)
                
            except Exception as e:
                return (image_path, {
                    "success": False,
                    "alt_text": "",
                    "error": str(e),
                    "attempts": 0
                })
        
        # Process in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Send all tasks
            futures = {executor.submit(process_single_image, img_path): img_path for img_path in image_paths}
            
            # Collect results as they complete
            for future in as_completed(futures):
                image_path, result = future.result()
                image_filename = os.path.basename(image_path)
                
                # Save result
                results[image_filename] = result

                if result["success"]:
                    alt_text = result["alt_text"]
                    # Nota: la generación de descripciones largas se maneja en una función separada
                    
                    # Crear archivo tag_
                    image_name_no_ext = os.path.splitext(image_filename)[0]
                    tag_filename = f"tag_{image_name_no_ext}.txt"
                    tag_path = os.path.join(output_dir, tag_filename)
                    
                    try:
                        with open(tag_path, "w", encoding="utf-8") as f:
                            f.write(f"alt: {alt_text}")  # Siempre escribir alt text
                        
                        successful_generations += 1
                        
                        # Estadísticas  
                        if result.get("fallback", False):
                            fallback_used += 1
                            print(f"⚠️ {image_filename}: Usando alt genérico tras {result.get('attempts', 0)} intentos")
                        else:
                            attempts = result.get('attempts', 1)
                            print(f"✅ {image_filename}: Alt descriptivo generado (intentos: {attempts}) - '{alt_text[:50]}{'...' if len(alt_text) > 50 else ''}'")
                    
                    except Exception as e:
                        print(f"❌ Error guardando {tag_filename}: {str(e)}")
                        failed_generations += 1
                else:
                    failed_generations += 1
                    error_msg = result.get("error", "Error desconocido")
                    print(f"❌ {image_filename}: {error_msg}")
                    # Escribir alt genérico para no dejar la imagen sin alt
                    try:
                        generic_alt = self._generate_fallback_alt(image_filename, context)
                        image_name_no_ext = os.path.splitext(image_filename)[0]
                        tag_filename = f"tag_{image_name_no_ext}.txt"
                        tag_path = os.path.join(output_dir, tag_filename)
                        with open(tag_path, "w", encoding="utf-8") as f:
                            f.write(f"alt: {generic_alt}")
                        successful_generations += 1
                        print(f"🛟 {image_filename}: Alt genérico escrito tras fallo")
                    except Exception as e:
                        print(f"❌ Error escribiendo alt genérico {image_filename}: {str(e)}")
        
        # Estadísticas finales
        summary = {
            "total_images": len(image_paths),
            "successful_generations": successful_generations,
            "failed_generations": failed_generations,
            "decorative_elements": decorative_elements,
            "long_desc_created": long_desc_created,
            "fallback_used": fallback_used,
            "results": results,
            "provider": "boto3"
        }
        
        print(f"📊 Resumen Boto3: {successful_generations} exitosos, {failed_generations} fallidos")
        print(f"   📝 Todos con descripción visual, ⚠️ Genéricos: {fallback_used}")
        
        return summary


def process_images_with_boto3(
    image_paths: List[str], 
    images_tags_dir: str, 
    context: Optional[str] = None,
    locale: str = "es",
    audience_profile: str = ""
) -> Dict[str, Any]:
    """
    Función de conveniencia para procesar imágenes con Boto3
    
    Args:
        image_paths: Lista de rutas de imágenes
        images_tags_dir: Directorio para archivos tag_
        context: Contexto para la generación
        locale: Código de idioma para generar alt text (ej: "es", "en", "fr"). Default: "es"
        audience_profile: Perfil de la audiencia objetivo para adaptar el lenguaje. Default: ""
        
    Returns:
        Dict con estadísticas del procesamiento
    """
    generator = Boto3AltGenerator(locale=locale, audience_profile=audience_profile)
    return generator.process_images_parallel(
        image_paths, 
        images_tags_dir, 
        context or "educational content"
    )
