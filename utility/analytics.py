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

from typing import Dict, Optional, Tuple
from database.crud import save_analytics, update_analytics_processing_time
from requests import Session
from function.llms.bedrock_invoke import get_default_model_ids, get_model_by_id
from icecream import ic
from datetime import datetime
from database.models import Request

class AnalyticsProcessor:
    def __init__(self, db: Session):
        self.db = db
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated_cost = 0
    
    def process_and_add_analytics(self, model: str, request_prompt: str, response: str) -> Tuple[int, int, float]:
        if model == 'default' or model == None:
            model = get_default_model_ids()["claude"]
        model_config = get_model_config(model)
        self.input_tokens = self.input_tokens + count_bedrock_tokens(request_prompt, model_config['token_rate'])
        self.output_tokens = self.output_tokens + count_bedrock_tokens(response, model_config['token_rate'])
        self.estimated_cost = self.estimated_cost + calculate_cost(model, self.input_tokens, self.output_tokens)
        return self.input_tokens, self.output_tokens, self.estimated_cost
    
    def get_analytics(self) -> Tuple[int, int, float]:
        return self.input_tokens, self.output_tokens, self.estimated_cost


def count_bedrock_tokens(text: str, token_rate: float = 6.0) -> int:
    """Count tokens for Bedrock models using model-specific rates."""
    if not text:
        return 0
    
    return len(text) // int(token_rate) + 1

def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate cost based on model pricing from database."""
    model_data = get_model_by_id(model.lower())
    ic(model_data)
    if not model_data:
        return 0.0
    
    input_cost = (input_tokens / 1000) * (model_data.input_price or 0)
    output_cost = (output_tokens / 1000) * (model_data.output_price or 0)
    ic(f"Input cost: {input_cost}, Output cost: {output_cost}", f"Total cost: {round(input_cost + output_cost, 8)}")
    return round(input_cost + output_cost, 8)

def get_model_config(model: str) -> Dict:
    """Get model configuration from database."""
    model_data = get_model_by_id(model.lower())
    if not model_data:
        return {'type': model, 'token_rate': 6.0}
    return {
        'type': model_data.provider.lower(),
        'token_rate': model_data.token_rate or 6.0
    }

async def process_and_save_analytics(
    db: Session,
    request_id: int,
    model: str,
    request_prompt: str,
    response: str,
    processing_time: float,
    model_params: Optional[Dict] = None,
    response_type: str = 'text',
    reference: Optional[str] = None,
):
    """Process analytics for Bedrock models."""
    error = None
    status = 'success'

    try:
        if model == 'default' or model == None:
            model = get_default_model_ids()["claude"]
        
        model_config = get_model_config(model)
        
        request_tokens = count_bedrock_tokens(request_prompt, model_config['token_rate'])
        response_tokens = count_bedrock_tokens(response, model_config['token_rate'])
        estimated_cost = calculate_cost(model, request_tokens, response_tokens)
        
        ic(f"Request tokens: {request_tokens}, Response tokens: {response_tokens}, Estimated cost: {estimated_cost}")

    except Exception as e:
        error = str(e)
        status = 'error'
        request_tokens = 0
        response_tokens = 0
        estimated_cost = 0

    save_analytics(
        db=db,
        request_id=request_id,
        model=model,
        request_token_count=request_tokens,
        response_token_count=response_tokens,
        processing_time=processing_time,
        estimated_cost=estimated_cost,
        error=error,
        model_parameters=model_params,
        response_type=response_type,
        status=status,
        reference=reference
    )

def update_processing_time(db: Session, request_id: int) -> float:
    request = db.query(Request).filter(Request.id == request_id).first()
    if not request:
        return 0.0
        
    current_time = datetime.now()
    processing_time = (current_time - request.created_at).total_seconds()
    
    update_analytics_processing_time(db, request_id, processing_time)
        
    return processing_time

