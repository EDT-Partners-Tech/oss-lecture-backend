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

import os
import boto3
from typing import Dict, List, Optional
from botocore.exceptions import ClientError
from utility.aws_clients import ssm_client

class ParameterStore:
    """
    A class to handle loading and managing parameters from AWS Systems Manager Parameter Store.
    """
    
    # Define category order for consistent output
    CATEGORY_ORDER = [
        'API',
        'AWS Core',
        'AWS Polly',
        'S3 Buckets',
        'Bedrock',
        'Cognito',
        'Database',
        'Other'
    ]
    
    # Define sensitive value patterns
    SENSITIVE_PATTERNS = ['secret', 'key', 'password', 'token']
    
    def __init__(self, region_name: Optional[str] = None):
        """
        Initialize the ParameterStore with AWS region.
        
        Args:
            region_name (str, optional): AWS region name. If not provided, will use AWS_REGION_NAME env var.
        """
        self.region_name = region_name or os.getenv('AWS_REGION_NAME')
        if not self.region_name:
            raise ValueError("AWS_REGION_NAME environment variable is not set")
        
        self.ssm_client = ssm_client
        self.base_path = '/lecture/global/'
        self.parameters: Dict[str, str] = {}
        self.categories: Dict[str, List[str]] = {}
    
    def _is_sensitive(self, param_name: str) -> bool:
        """Check if a parameter name indicates a sensitive value."""
        return any(pattern in param_name.lower() for pattern in self.SENSITIVE_PATTERNS)
    
    def _mask_value(self, value: str) -> str:
        """Mask sensitive values."""
        return '********' if value else value
    
    def _categorize_parameter(self, param_name: str) -> str:
        """Categorize a parameter based on its prefix."""
        prefix = next((prefix for prefix in ['API_', 'AWS_', 'BEDROCK_', 'COGNITO_', 'DATABASE_'] 
                      if param_name.startswith(prefix)), None)
        
        if prefix:
            if prefix == 'AWS_':
                if param_name.startswith('AWS_S3_'):
                    return 'S3 Buckets'
                elif param_name.startswith('AWS_POLLY_'):
                    return 'AWS Polly'
                else:
                    return 'AWS Core'
            return prefix.replace('_', ' ').strip()
        return 'Other'
    
    def load_parameters(self) -> Dict[str, str]:
        """
        Load parameters from SSM and update environment variables.
        
        Returns:
            Dict[str, str]: Dictionary of parameter names and values
        """
        print(f"\n=== Loading parameters from SSM in region {self.region_name} ===")
        
        try:
            found_parameters = set()
            empty_parameters = []
            
            # Get parameters by path
            print(f"\nChecking path: {self.base_path}")
            try:
                paginator = self.ssm_client.get_paginator('get_parameters_by_path')
                for page in paginator.paginate(
                    Path=self.base_path,
                    Recursive=True,
                    WithDecryption=True
                ):
                    for param in page['Parameters']:
                        param_name = param['Name'].replace(self.base_path, '').replace('/', '_').upper()
                        param_value = param['Value']
                        self.parameters[param_name] = param_value
                        found_parameters.add(param_name)
                        
                        if not param_value or param_value.strip() == '':
                            empty_parameters.append(param_name)
                        else:
                            masked_value = self._mask_value(param_value) if self._is_sensitive(param_name) else param_value
                            print(f"Found: {param_name} = {masked_value}")
                
                print(f"\nSSM Response Status: 200")
                print(f"Total parameters found: {len(self.parameters)}")
                
            except ClientError as e:
                print(f"Error getting parameters by path: {e.response['Error']['Message']}")
            
            if not self.parameters:
                print("\nWarning: No parameters were found in SSM")
                return {}
            
            # Report empty parameters
            if empty_parameters:
                print("\nEmpty parameters in SSM:")
                for param in sorted(empty_parameters):
                    print(f"  {param}")
            
            # Update environment variables
            os.environ.update(self.parameters)
            
            # Categorize parameters
            self._categorize_parameters()
            
            # Print organized parameters
            self._print_parameters()
            
            return self.parameters
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"\nError loading parameters from SSM:")
            print(f"Error Code: {error_code}")
            print(f"Error Message: {error_message}")
            if error_code == 'ParameterNotFound':
                print("No parameters found in the specified path")
                return {}
            raise ValueError(f"Failed to load parameters from SSM: {error_message}")
    
    def _categorize_parameters(self) -> None:
        """Categorize all loaded parameters."""
        self.categories = {}
        for param_name in self.parameters.keys():
            category = self._categorize_parameter(param_name)
            if category not in self.categories:
                self.categories[category] = []
            self.categories[category].append(param_name)
    
    def _print_parameters(self) -> None:
        """Print parameters in an organized format."""
        print(f"\nParameters loaded from SSM ({len(self.parameters)} total):")
        print("=" * 50)
        
        # Print categories in specified order
        for category in self.CATEGORY_ORDER:
            if category in self.categories and self.categories[category]:
                print(f"\n{category}:")
                print("-" * len(category))
                for key in sorted(self.categories[category]):
                    masked_value = self._mask_value(self.parameters[key]) if self._is_sensitive(key) else self.parameters[key]
                    print(f"  {key}: {masked_value}")
        
        # Print any categories that weren't in the predefined order
        for category in sorted(self.categories.keys()):
            if category not in self.CATEGORY_ORDER and self.categories[category]:
                print(f"\n{category}:")
                print("-" * len(category))
                for key in sorted(self.categories[category]):
                    masked_value = self._mask_value(self.parameters[key]) if self._is_sensitive(key) else self.parameters[key]
                    print(f"  {key}: {masked_value}")
    
    def get_parameter(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a parameter value by name.
        
        Args:
            name (str): Parameter name
            default (str, optional): Default value if parameter not found
            
        Returns:
            str: Parameter value or default if not found
        """
        return self.parameters.get(name, default)
    
    def get_parameters_by_category(self, category: str) -> Dict[str, str]:
        """
        Get all parameters in a specific category.
        
        Args:
            category (str): Category name
            
        Returns:
            Dict[str, str]: Dictionary of parameter names and values in the category
        """
        if category not in self.categories:
            return {}
        return {name: self.parameters[name] for name in self.categories[category]} 