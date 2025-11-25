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

from botocore.exceptions import ClientError
from fastapi import HTTPException
from typing import Optional
from utility.aws_clients import ssm_client

class SSMParameterStore:
    def __init__(self, client=None):
        self.client = client or ssm_client

    def get_parameter(self, parameter_name: str, decrypt: bool = True) -> Optional[str]:
        """
        Get a parameter from the Parameter Store.
        
        Args:
            parameter_name (str): Name of the parameter to get
            decrypt (bool): If True, decrypt the parameter if it is encrypted
            
        Returns:
            str: Value of the parameter
            
        Raises:
            ClientError: If there is an error getting the parameter
        """
        try:
            response = self.client.get_parameter(
                Name=parameter_name,
                WithDecryption=decrypt
            )
            return response['Parameter']['Value']
        except ClientError as e:
            print(f"Error getting the parameter {parameter_name}: {str(e)}")
            return None

    def get_parameters_by_path(
        self,
        path: str,
        recursive: bool = False,
        decrypt: bool = True
    ) -> list:
        """
        Get multiple parameters that share a path prefix.
        
        Args:
            path (str): Base path to search for parameters
            recursive (bool): If True, search in subdirectories
            decrypt (bool): If True, decrypt the parameters if they are encrypted
            
        Returns:
            list: List of parameters found
            
        Raises:
            ClientError: If there is an error getting the parameters
        """
        try:
            parameters = []
            paginator = self.client.get_paginator('get_parameters_by_path')
            
            for page in paginator.paginate(
                Path=path,
                Recursive=recursive,
                WithDecryption=decrypt
            ):
                parameters.extend(page['Parameters'])
                
            return parameters
        except ClientError as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error getting parameters from the path {path}: {str(e)}"
            ) 