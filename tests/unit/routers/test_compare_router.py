# 
# Copyright 2025 EDT&Partners
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 

import json
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import compare
from routers.compare import get_db
from utility.auth import oauth2_scheme
from database.models import User, UserRole

app = FastAPI()
app.include_router(compare.router, prefix="/compare")

@pytest.fixture(scope="function")
def client(mock_cognito_token_payload):
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[oauth2_scheme] = lambda: "fake-jwt-token"

    with patch("utility.auth.jose_jwt.get_unverified_claims") as mock_get_claims:
    
        mock_get_claims.return_value = {"cognito:username": "dummy_user_id"}
        
        mock_validator = AsyncMock()
        mock_validator.validate_token.return_value = mock_cognito_token_payload
    
        with patch.dict("utility.auth.VALIDATOR_MAP", {"cognito": mock_validator}): 
            client = TestClient(app)
            yield client

    app.dependency_overrides.clear()

# Clase dummy para simular un objeto ComparisonEngine
class DummyComparisonEngine:
    def __init__(self, content, status="SUCCESS"):
        self.content = content
        self.status = status

# ---------------------------------------------------------------------------
# Test para GET /compare/{type}/ (lista de registros)
def test_get_comparison_engine_list(client):
    dummy_list = [{
        "id": str(uuid.uuid4()),        # UUID válido
        "name": "Dummy Comparison",     # Campo requerido agregado
        "content": "{}",
        "status": "SUCCESS"
    }]
    with patch("routers.compare.get_comparison_engine_documents_by_user_id", new=AsyncMock(return_value=dummy_list)):
        response = client.get("/compare/document/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Verifica que el id sea un UUID válido
        uuid.UUID(data[0]["id"])
        assert data[0]["name"] == "Dummy Comparison"

# ---------------------------------------------------------------------------
# Test para GET /compare/data/{comparison_id}/
def test_get_comparison_engine(client):
    # Simular contenido sin fragmento markdown_code para que la función procese bien.
    dummy_content = json.dumps({"result": "ok"})
    dummy_engine = DummyComparisonEngine(content=dummy_content, status="SUCCESS")
    with patch("routers.compare.get_comparison_engine_document_by_id", new=AsyncMock(return_value=dummy_engine)):
        response = client.get("/compare/data/12345/")
        assert response.status_code == 200
        data = response.json()
        # Se espera que la respuesta incluya "result" y un campo markdown_code vacío
        assert data["result"]["result"] == "ok"
        assert "markdown_code" in data["result"]

# ---------------------------------------------------------------------------
# Test para DELETE /compare/{comparison_id}/
def test_delete_comparison_engine(client):
    dummy_engine = DummyComparisonEngine(content="{}", status="SUCCESS")
    with patch("routers.compare.get_comparison_engine_document_by_id", new=AsyncMock(return_value=dummy_engine)), \
         patch("routers.compare.delete_comparison_engine_by_id", new=AsyncMock(return_value=None)):
        response = client.delete("/compare/12345/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Comparison successfully deleted"

# ---------------------------------------------------------------------------
# Test para POST /compare/document-status y /compare/resume-status
dummy_request = {
    "process_id": str(uuid.uuid4()),
    "name": "Test Comparison",
    "description": "Test Description",
    "document1_id": "doc1",
    "document2_id": "doc2",
    "rules_ids": ["rule1", "rule2"],
    "language": "en",
    "model": "test-model",
    "config_id": "" 
}

@patch("routers.compare.process_comparison", new_callable=AsyncMock)
def test_compare_document_status(mock_process, client):
    response = client.post("/compare/document-status", json=dummy_request)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Comparison start successfully"

@patch("routers.compare.process_comparison", new_callable=AsyncMock)
def test_compare_resume_status(mock_process, client):
    response = client.post("/compare/resume-status", json=dummy_request)
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Comparison start successfully"

# ---------------------------------------------------------------------------
# Test para GET /compare/rules/{type}/
def test_get_comparison_rules(client):
    dummy_rules = [{"id": "rule1", "name": "Rule 1", "data": {}}]
    with patch("routers.compare.get_comparison_rules_by_user_id_and_type", new=AsyncMock(return_value=dummy_rules)):
        response = client.get("/compare/rules/document/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert data[0]["id"] == "rule1"

# ---------------------------------------------------------------------------
# Test para GET /compare/rule/data/{id}/
def test_get_comparison_rule_by_id(client):
    dummy_rule = {"id": "rule1", "name": "Rule 1", "data": {}}
    with patch("routers.compare.get_comparison_rule_by_id", new=AsyncMock(return_value=dummy_rule)):
        response = client.get("/compare/rule/data/rule1/")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "rule1"

# ---------------------------------------------------------------------------
# Test para POST /compare/rule/{type}/ (crear regla)
def test_create_comparison_rule(client):
    new_rule_req = {
        "name": "New Rule",
        "description": "Rule description",
        "data": {"rules": []}
    }
    with patch("routers.compare.save_comparison_rule", new=AsyncMock(return_value="new-rule-id")):
        response = client.post("/compare/rule/document/", json=new_rule_req)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Comparison rule created successfully"
        assert data["rule_id"] == "new-rule-id"

# ---------------------------------------------------------------------------
# Test para DELETE /compare/rule/{rule_id}/
def test_delete_comparison_rule(client):
    dummy_rule = {"id": "rule1", "name": "Rule 1", "data": {}}
    with patch("routers.compare.get_comparison_rule_by_id", new=AsyncMock(return_value=dummy_rule)), \
         patch("routers.compare.delete_comparison_rule_by_id", new=AsyncMock(return_value=None)):
        response = client.delete("/compare/rule/rule1/")
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Comparison successfully deleted"

# ---------------------------------------------------------------------------
# Test para POST /compare/convert/
def test_convert_file(client):
    # Simular contenido de entrada
    convert_payload = {
        "input_data": "This is **bold** text",
        "input_format": "markdown",
        "output_format": "html"
    }
    # Se parchea pypandoc.convert_file para crear un fichero de salida simulado
    def fake_convert(input_path, output_format, format, outputfile):
        with open(outputfile, "w", encoding="utf-8") as f:
            f.write("<p>This is <strong>bold</strong> text</p>")
        return ""

    with patch("routers.compare.pypandoc.convert_file", side_effect=fake_convert):
        response = client.post("/compare/convert/", json=convert_payload)
        assert response.status_code == 200
        # Verificamos que se retorne un FileResponse leyendo el fichero generado
        content = response.content.decode("utf-8")
        assert "This is <strong>bold</strong> text" in content

# Test upload file endpoint in compare.py
def test_upload_file_compare(client):
    # Create a mock file content
    file_content = b"This is a test PDF"
    
    test_user = User(id="test-user-id", cognito_id="test-cognito-id", name="Test User", email="test@example.com", role=UserRole.teacher)

    with patch("routers.compare.upload_file_to_s3", new_callable=AsyncMock, return_value="s3://test-bucket/test.pdf"), \
         patch("routers.compare.save_comparison_document_data", new_callable=AsyncMock, return_value="doc-123"), \
         patch("routers.compare.get_user_by_cognito_id", return_value=test_user), \
         patch("uuid.uuid4", return_value=uuid.UUID('12345678123456781234567812345678')):
        
        response = client.post(
            "/compare/upload/",
            files={"files": ("test.pdf", file_content)}
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Files uploaded successfully"
        assert response.json()["files"][0]["id"] == "doc-123"
        assert response.json()["files"][0]["filename"] == "test.pdf"
        assert response.json()["files"][0]["s3_uri"] == "s3://test-bucket/test.pdf"
        assert response.json()["process_id"] == "12345678-1234-5678-1234-567812345678"