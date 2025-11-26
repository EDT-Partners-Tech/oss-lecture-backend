<!--
 Copyright 2022 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
-->

# Construcción de ARNs para Modelos de AWS Bedrock

## Descripción General

Este documento explica cómo construir correctamente los ARNs (Amazon Resource Names) para invocar modelos de AWS Bedrock, diferenciando entre modelos de inferencia personalizados y modelos foundation estándar.

## Código de Referencia

```python
account_id = get_caller_identity()
region, suffix = get_model_region(self.model_id)
model = get_model_by_id(self.model_id)

if not model:
    raise ValueError(f"Model not found for ID: {self.model_id}")

if is_inference_model(self.model_id):
    model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{self.model_id}"
else:
    model_arn = f"arn:aws:bedrock:{region}::foundation-model/{self.model_id}"
```

## Funciones Auxiliares Requeridas

### 1. `get_caller_identity()`

**Propósito**: Obtiene el ID de la cuenta AWS actual.

**Implementación**:
```python
import boto3

def get_caller_identity() -> str:
    """Obtiene el ID de la cuenta AWS actual"""
    sts_client = boto3.client('sts')
    response = sts_client.get_caller_identity()
    return response['Account']
```

**Retorna**: String con el ID de la cuenta AWS (ej: "123456789012")

### 2. `get_model_region(model_id)`

**Propósito**: Obtiene la región y el sufijo de región para un modelo específico.

**Implementación**:
```python
def get_model_region(model_id: str) -> tuple:
    """
    Obtiene la región y sufijo de región para un modelo
    
    Args:
        model_id: ID del modelo (ej: "anthropic.claude-3-7-sonnet-20250219-v1:0")
        
    Returns:
        tuple: (region, suffix) o (None, None) si no se encuentra
    """
    # Esta función debe consultar tu base de datos o configuración
    # donde tengas almacenada la información de los modelos
    
    # Ejemplo de estructura de datos esperada:
    models_config = {
        "anthropic.claude-3-7-sonnet-20250219-v1:0": {
            "region": "us-east-1",
            "suffix": "us-east-1"
        },
        "amazon.titan-text-express-v1": {
            "region": "us-east-1", 
            "suffix": "us-east-1"
        }
    }
    
    model_info = models_config.get(model_id)
    if model_info:
        return model_info["region"], model_info["suffix"]
    
    return None, None
```

**Retorna**: Tupla `(region, suffix)` o `(None, None)` si no se encuentra el modelo.

### 3. `get_model_by_id(model_id)`

**Propósito**: Obtiene la información completa del modelo desde la base de datos.

**Implementación**:
```python
def get_model_by_id(model_id: str):
    """
    Obtiene información del modelo por su ID
    
    Args:
        model_id: ID del modelo
        
    Returns:
        Objeto del modelo o None si no se encuentra
    """
    # Consulta a tu base de datos
    # Ejemplo con SQLAlchemy:
    # model = session.query(AIModel).filter(AIModel.identifier == model_id).first()
    # return model
    
    # Para implementación simple, puedes usar un diccionario:
    models_db = {
        "anthropic.claude-3-7-sonnet-20250219-v1:0": {
            "identifier": "anthropic.claude-3-7-sonnet-20250219-v1:0",
            "provider": "Anthropic",
            "region": "us-east-1",
            "max_input_tokens": 200000,
            "inference": False
        }
    }
    
    return models_db.get(model_id)
```

**Retorna**: Objeto del modelo o `None` si no se encuentra.

### 4. `is_inference_model(model_id)`

**Propósito**: Determina si un modelo es un modelo de inferencia personalizado.

**Implementación**:
```python
def is_inference_model(model_id: str) -> bool:
    """
    Determina si un modelo es de inferencia personalizado
    
    Args:
        model_id: ID del modelo
        
    Returns:
        bool: True si es modelo de inferencia, False si es foundation model
    """
    # Lista de modelos de inferencia personalizados
    inference_models = [
        "anthropic.claude-3-7-sonnet-20250219-v1:0",  # Ejemplo
        # Agregar otros modelos de inferencia aquí
    ]
    
    return model_id in inference_models
    
    # Alternativamente, consultar la base de datos:
    # model = get_model_by_id(model_id)
    # return model.inference if model else False
```

**Retorna**: `True` si es modelo de inferencia, `False` si es foundation model.

## Construcción de ARNs

### Para Modelos de Inferencia Personalizados

**Formato**:
```
arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}
```

**Ejemplo**:
```
arn:aws:bedrock:us-east-1:123456789012:inference-profile/us-east-1.anthropic.claude-3-7-sonnet-20250219-v1:0
```

### Para Modelos Foundation Estándar

**Formato**:
```
arn:aws:bedrock:{region}::foundation-model/{model_id}
```

**Ejemplo**:
```
arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-text-express-v1
```

## Implementación Completa

```python
import boto3
from typing import Optional, Tuple

class BedrockModelARNBuilder:
    """Constructor de ARNs para modelos de AWS Bedrock"""
    
    def __init__(self):
        self.sts_client = boto3.client('sts')
    
    def get_caller_identity(self) -> str:
        """Obtiene el ID de la cuenta AWS actual"""
        response = self.sts_client.get_caller_identity()
        return response['Account']
    
    def get_model_region(self, model_id: str) -> Tuple[Optional[str], Optional[str]]:
        """Obtiene región y sufijo para un modelo"""
        # Implementar según tu sistema de configuración
        models_config = {
            "anthropic.claude-3-7-sonnet-20250219-v1:0": {
                "region": "us-east-1",
                "suffix": "us-east-1"
            }
        }
        
        model_info = models_config.get(model_id)
        if model_info:
            return model_info["region"], model_info["suffix"]
        
        return None, None
    
    def get_model_by_id(self, model_id: str):
        """Obtiene información del modelo"""
        # Implementar consulta a base de datos
        models_db = {
            "anthropic.claude-3-7-sonnet-20250219-v1:0": {
                "identifier": "anthropic.claude-3-7-sonnet-20250219-v1:0",
                "provider": "Anthropic",
                "inference": True
            }
        }
        return models_db.get(model_id)
    
    def is_inference_model(self, model_id: str) -> bool:
        """Determina si es modelo de inferencia"""
        model = self.get_model_by_id(model_id)
        return model.get("inference", False) if model else False
    
    def build_model_arn(self, model_id: str) -> str:
        """
        Construye el ARN completo para un modelo de Bedrock
        
        Args:
            model_id: ID del modelo
            
        Returns:
            str: ARN completo del modelo
            
        Raises:
            ValueError: Si el modelo no se encuentra
        """
        # Obtener información necesaria
        account_id = self.get_caller_identity()
        region, suffix = self.get_model_region(model_id)
        model = self.get_model_by_id(model_id)
        
        # Validar que el modelo existe
        if not model:
            raise ValueError(f"Model not found for ID: {model_id}")
        
        # Construir ARN según el tipo de modelo
        if self.is_inference_model(model_id):
            model_arn = f"arn:aws:bedrock:{region}:{account_id}:inference-profile/{suffix}.{model_id}"
        else:
            model_arn = f"arn:aws:bedrock:{region}::foundation-model/{model_id}"
        
        return model_arn

# Ejemplo de uso
if __name__ == "__main__":
    builder = BedrockModelARNBuilder()
    
    # Modelo de inferencia personalizado
    inference_model_id = "anthropic.claude-3-7-sonnet-20250219-v1:0"
    inference_arn = builder.build_model_arn(inference_model_id)
    print(f"Inference Model ARN: {inference_arn}")
    
    # Modelo foundation estándar
    foundation_model_id = "amazon.titan-text-express-v1"
    foundation_arn = builder.build_model_arn(foundation_model_id)
    print(f"Foundation Model ARN: {foundation_arn}")
```

## Consideraciones Importantes

### 1. **Permisos AWS**
Asegúrate de que tu cuenta AWS tenga los permisos necesarios:
- `bedrock:InvokeModel` para modelos foundation
- `bedrock:InvokeModel` para modelos de inferencia personalizados
- `sts:GetCallerIdentity` para obtener el ID de cuenta

### 2. **Regiones Disponibles**
Los modelos de Bedrock están disponibles en regiones específicas. Verifica que la región sea correcta para tu modelo.

### 3. **Modelos de Inferencia**
Los modelos de inferencia personalizados requieren:
- Que el modelo esté desplegado en tu cuenta
- Que tengas permisos para acceder al perfil de inferencia
- Que el sufijo de región coincida con la región del modelo

### 4. **Manejo de Errores**
Implementa manejo de errores robusto para:
- Modelos no encontrados
- Regiones no disponibles
- Permisos insuficientes
- Errores de red

## Ejemplo de Integración con Bedrock

```python
import boto3
import json

def invoke_bedrock_model(model_id: str, prompt: str):
    """Ejemplo de invocación de modelo con ARN construido dinámicamente"""
    
    # Construir ARN
    builder = BedrockModelARNBuilder()
    model_arn = builder.build_model_arn(model_id)
    
    # Crear cliente Bedrock
    bedrock_client = boto3.client('bedrock-runtime')
    
    # Preparar payload
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1000,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    # Invocar modelo
    response = bedrock_client.invoke_model(
        modelId=model_arn,
        body=json.dumps(body),
        contentType="application/json"
    )
    
    # Procesar respuesta
    response_body = json.loads(response['body'].read())
    return response_body['content'][0]['text']
```

## Conclusión

La construcción correcta de ARNs para modelos de AWS Bedrock es esencial para la invocación exitosa de modelos. La diferencia principal radica en:

- **Modelos Foundation**: Usan el formato estándar sin ID de cuenta
- **Modelos de Inferencia**: Requieren el ID de cuenta y el sufijo de región

Esta implementación te permitirá manejar ambos tipos de modelos de manera transparente y robusta.
