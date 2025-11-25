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

import logging
from uuid import UUID
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from database.crud import get_group_by_id

logger = logging.getLogger(__name__)

def generate_lti_private_key() -> str:
    """
    Generate a new RSA private key for LTI 1.3 authentication.
    
    Returns:
        str: The private key in PEM format as a string
    """
    try:
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        # Get private key in PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        return private_pem.decode('utf-8')
    
    except Exception as e:
        logger.error(f"Error generating LTI private key: {e}")
        raise RuntimeError(f"Failed to generate LTI private key: {e}")


def ensure_group_has_lti_private_key(db: Session, group_id: UUID):
    """
    Ensure that a group has an LTI private key assigned to it.
    If the group doesn't have a private key, generate a new one and assign it.
    
    Args:
        db (Session): SQLAlchemy database session
        group_id (UUID): The ID of the group to check/update
    
    Returns:
        str: The private key in PEM format (decrypted)
    
    Raises:
        ValueError: If the group is not found
        RuntimeError: If there's an error generating or saving the private key
    """
    try:
        # Get the group
        group = get_group_by_id(db, group_id)
        if not group:
            raise ValueError(f"Group with ID {group_id} not found")
        
        # Check if the group already has a private key
        if group.lti_private_key:
            logger.info(f"Group {group_id} already has an LTI private key")
            return
        
        # Generate a new private key
        logger.info(f"Generating new LTI private key for group {group_id}")
        private_key_pem = generate_lti_private_key()
        
        # Assign the private key to the group (this will be encrypted automatically)
        group.lti_private_key = private_key_pem
        
        # Save changes to database
        db.commit()
        db.refresh(group)
        
        logger.info(f"Successfully generated and assigned LTI private key for group {group_id}")
    except ValueError:
        # Re-raise ValueError as is
        raise
    except Exception as e:
        # Rollback transaction on any error
        db.rollback()
        logger.error(f"Error creating LTI private key for group {group_id}: {e}")
        raise RuntimeError(f"Failed to create LTI private key for group: {e}")
