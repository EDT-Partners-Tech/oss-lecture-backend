# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import uuid
from routers.chatbot import router
from database.db import get_db
from database.schemas import ChatbotCreate
from utility.auth import oauth2_scheme
from types import SimpleNamespace
from utility.tokens import CognitoTokenPayload

app = FastAPI()
app.include_router(router, prefix="/api/v1/chatbot", tags=["chatbot"])

@pytest.fixture
def mock_db():
    return Mock()

@pytest.fixture
def client(mock_db, mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
        
        # Mock the unverified claims to return cognito format
        mock_get_claims.return_value = {"cognito:username": "test-user"}
        
        # Mock the validator to return our test token data
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload

        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}):
            # Create test client
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_process_document_with_images(mock_db):
    # Crear un mock para el archivo UploadFile
    mock_file = Mock()
    mock_file.read = AsyncMock(return_value=b"%PDF-1.4\n%EOF")
    mock_file.filename = "test.pdf"
    
    # Crear un objeto ChatbotCreate para pasar como parámetro
    chatbot_data = ChatbotCreate(
        id=str(uuid.uuid4()),
        name="Test Bot",
        system_prompt="Test prompt",
        user_id=str(uuid.uuid4()),
        status="processing",
        session_id=str(uuid.uuid4()),
        memory_id=str(uuid.uuid4()),
        resource_data="{}"
    )
    
    # Configurar el mock para PDFDocumentProcessor
    with patch("routers.chatbot.PDFDocumentProcessor") as mock_processor_class:
        # Configurar el mock para que process_document devuelva un diccionario con datos realistas
        mock_processor = Mock()
        mock_processor.process_document = AsyncMock(return_value={
            "chatbot_name": chatbot_data.name,
            "markdown_content": ["# Test Document", "This is a test document with images"]
        })
        mock_processor_class.return_value = mock_processor
        
        # Llamamos directamente a la función
        from routers.chatbot import process_document_with_images
        result = await process_document_with_images(mock_db, mock_file, chatbot_data)
        
        # Verificar que se creó el procesador con los parámetros correctos
        mock_processor_class.assert_called_once_with(mock_db, mock_file, chatbot_data)
        
        # Verificar que se llamó al método process_document
        mock_processor.process_document.assert_called_once()
        
        # Verificar el resultado
        assert result["chatbot_name"] == chatbot_data.name
        assert len(result["markdown_content"]) == 2
        assert result["markdown_content"][0] == "# Test Document"
        assert result["markdown_content"][1] == "This is a test document with images"

@pytest.mark.asyncio
async def test_get_chatbots(client, mock_db):
    # Crear un mock para el usuario
    mock_user = SimpleNamespace(id=str(uuid.uuid4()))
    
    # Crear un mock para los chatbots
    mock_chatbot = SimpleNamespace(
        id=str(uuid.uuid4()),
        name="Test Chatbot",
        system_prompt="You are a helpful assistant",
        updated_at="2025-07-24T16:32:33", # Usando fecha actual como ejemplo
        status="completed"
    )
    
    # Crear un mock para los materiales del chatbot
    mock_material = SimpleNamespace(id=str(uuid.uuid4()), title="Test Material")

    mock_get_user = Mock(return_value=mock_user)
    mock_get_chatbots = AsyncMock(return_value=[mock_chatbot])
    mock_get_materials = AsyncMock(return_value=[mock_material])
    
    with patch("routers.chatbot.get_chatbots_by_user_id", new=mock_get_chatbots), \
         patch("routers.chatbot.get_user_by_cognito_id", new=mock_get_user), \
         patch("routers.chatbot.get_chatbot_materials_by_chatbot_id_with_is_main_true", new=mock_get_materials):
        # Llamar al endpoint
        response = client.get("/api/v1/chatbot/")
        
        # Verificar que se llamaron las funciones correctas
        mock_get_user.assert_called_once()
        mock_get_chatbots.assert_called_once_with(mock_db, mock_user.id)
        mock_get_materials.assert_called_once_with(mock_db, mock_chatbot.id)
        
        # Verificar la respuesta
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result, list)
        assert len(result) == 1
        
        # Verificar el contenido de la respuesta
        chatbot_data = result[0]
        assert chatbot_data["chatbot_id"] == mock_chatbot.id
        assert chatbot_data["chatbot_name"] == mock_chatbot.name
        assert chatbot_data["chatbot_system_prompt"] == mock_chatbot.system_prompt
        assert chatbot_data["updated_at"] == mock_chatbot.updated_at
        
        # Verificar los materiales
        assert "materials" in chatbot_data
        assert len(chatbot_data["materials"]) == 1
        material_data = chatbot_data["materials"][0]
        assert material_data["id"] == mock_material.id
        assert material_data["name"] == mock_material.title

@pytest.mark.asyncio
async def test_get_chatbot_resources(client, mock_db):
    # Crear un mock para el usuario
    mock_user = Mock()
    mock_user.id = str(uuid.uuid4())
    
    # Crear un mock para los chatbots
    mock_chatbot = Mock()
    mock_chatbot.id = str(uuid.uuid4())
    
    # Crear un mock para los materiales del chatbot
    mock_chatbot_material = Mock()
    mock_chatbot_material.id = str(uuid.uuid4())
    mock_chatbot_material.title = "Test Chatbot Material"
    
    # Crear un mock para los cursos
    mock_course = Mock()
    mock_course.id = str(uuid.uuid4())
    mock_course.title = "Test Course"
    mock_course.knowledge_base_id = str(uuid.uuid4())
    mock_course.settings = None
    
    # Crear un mock para los materiales del curso
    mock_course_material = Mock()
    mock_course_material.id = str(uuid.uuid4())
    mock_course_material.title = "Test Course Material"
    mock_course_material.type = "application/pdf"
    
    with patch("routers.chatbot.get_chatbots_by_user_id") as mock_get, \
         patch("routers.chatbot.get_user_by_cognito_id") as mock_get_user, \
         patch("routers.chatbot.get_chatbot_materials_by_chatbot_id_with_is_main_true") as mock_materials, \
         patch("routers.chatbot.get_teacher_courses") as mock_courses, \
         patch("routers.chatbot.get_materials_by_course") as mock_course_materials:
        # Configurar los mocks
        mock_get_user.return_value = mock_user
        mock_get.return_value = [mock_chatbot]
        mock_materials.return_value = [mock_chatbot_material]
        mock_courses.return_value = [mock_course]
        mock_course_materials.return_value = [mock_course_material]
        
        # Llamar al endpoint
        response = client.get("/api/v1/chatbot/resources")
        
        # Verificar que se llamaron las funciones correctas
        mock_get_user.assert_called_once()
        mock_get.assert_called_once_with(mock_db, mock_user.id)
        mock_materials.assert_called_once_with(mock_db, mock_chatbot.id)
        mock_courses.assert_called_once_with(mock_db, mock_user.id)
        mock_course_materials.assert_called_once_with(mock_db, mock_course.id)
        
        # Verificar la respuesta
        assert response.status_code == 200
        result = response.json()
        assert isinstance(result, list)
        
        # Verificar que hay 3 recursos (1 material de chatbot, 1 material de curso, 1 base de conocimiento)
        assert len(result) == 3
        
        # Verificar el material del chatbot
        chatbot_material = next(item for item in result if item["resource_type"] == "chatbot_material")
        assert chatbot_material["resource_id"] == mock_chatbot_material.id
        assert chatbot_material["resource_name"] == mock_chatbot_material.title
        
        # Verificar el material del curso
        course_material = next(item for item in result if item["resource_type"] == "course_material")
        assert course_material["resource_id"] == mock_course_material.id
        assert course_material["resource_name"] == mock_course_material.title
        
        # Verificar la base de conocimiento del curso
        knowledge_base = next(item for item in result if item["resource_type"] == "course_knowledge_base")
        assert knowledge_base["resource_id"] == mock_course.knowledge_base_id
        assert knowledge_base["resource_name"] == mock_course.title

@pytest.mark.asyncio
async def test_get_chatbot_by_id(client, mock_db):
    # Crear un mock para el usuario
    mock_user = Mock()
    mock_user.id = str(uuid.uuid4())
    
    # Crear un mock para el chatbot
    mock_chatbot = Mock()
    mock_chatbot.id = str(uuid.uuid4())
    mock_chatbot.name = "Test Chatbot"
    mock_chatbot.status = "completed"
    mock_chatbot.system_prompt = "You are a helpful assistant"
    
    # Crear un mock para los mensajes
    mock_message = Mock()
    mock_message.id = str(uuid.uuid4())
    mock_message.content = "Original content"
    mock_message.role = "user"
    mock_message.created_at = "2023-01-01T00:00:00"
    mock_message.updated_at = "2023-01-01T00:00:00"
    
    chatbot_id = str(uuid.uuid4())
    with patch("routers.chatbot.get_chatbot_by_id") as mock_get, \
         patch("routers.chatbot.get_user_by_cognito_id") as mock_get_user, \
         patch("routers.chatbot.get_messages_by_chatbot_id") as mock_messages, \
         patch("routers.chatbot.ChatbotProcessor") as mock_processor_class:
        # Configurar los mocks
        mock_get_user.return_value = mock_user
        mock_get.return_value = mock_chatbot
        mock_messages.return_value = [mock_message]
        
        # Configurar el mock para el procesador
        mock_processor = Mock()
        mock_processor.process_markdown_images = AsyncMock(return_value="Processed content")
        mock_processor.set_agent = AsyncMock()
        mock_processor_class.return_value = mock_processor
        
        # Llamar al endpoint
        response = client.get(f"/api/v1/chatbot/{chatbot_id}")
        
        # Verificar que se llamaron las funciones correctas
        mock_get_user.assert_called_once()
        mock_get.assert_called_once_with(mock_db, chatbot_id)
        mock_messages.assert_called_once_with(mock_db, chatbot_id)
        mock_processor_class.assert_called_once_with(mock_db, "")
        mock_processor.process_markdown_images.assert_called_once_with("Original content")
        
        # Verificar la respuesta
        assert response.status_code == 200
        result = response.json()
        
        # Verificar el contenido de la respuesta
        assert result["chatbot_id"] == mock_chatbot.id
        assert result["chatbot_name"] == mock_chatbot.name
        assert result["chatbot_status"] == mock_chatbot.status
        assert result["chatbot_system_prompt"] == mock_chatbot.system_prompt
        
        # Verificar los mensajes
        assert "messages" in result
        assert len(result["messages"]) == 1
        message_data = result["messages"][0]
        assert message_data["id"] == mock_message.id
        assert message_data["content"] == "Processed content"
        assert message_data["role"] == mock_message.role
        assert message_data["created_at"] == mock_message.created_at
        assert message_data["updated_at"] == mock_message.updated_at

@pytest.mark.asyncio
async def test_delete_chatbot(client, mock_db):
    chatbot_id = str(uuid.uuid4())
    with patch("routers.chatbot.delete_chatbot_by_id") as mock_delete, \
         patch("routers.chatbot.get_user_by_cognito_id") as mock_get_user:
        mock_get_user.return_value = Mock(id=str(uuid.uuid4()))  # Cambiado a UUID válido
        mock_delete.return_value = None
        response = client.delete(f"/api/v1/chatbot/{chatbot_id}")
        assert response.status_code == 200
        assert "message" in response.json()

