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
import sys
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
_LOGGING_INITIALIZED = False

def setup_logging(module_name=None):
    global _LOGGING_INITIALIZED
    if _LOGGING_INITIALIZED:
        return logging.getLogger(module_name or __name__)

    _LOGGING_INITIALIZED = True

    # Create the root logger
    logger = logging.getLogger()
    logger.setLevel(LOG_LEVEL)

    # Clear existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create StreamHandler explicitly with sys.stdout
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setLevel(LOG_LEVEL)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    stream_handler.setFormatter(formatter)

    # Add handler to root logger
    logger.addHandler(stream_handler)

    # Suppress noisy 3rd-party libraries by setting their log level higher (ERROR)
    noisy_loggers = [
        "botocore",
        "botocore.hooks",
        "botocore.endpoint",
        "botocore.credentials",
        "botocore.utils",
        "urllib3",
        "urllib3.connectionpool",
        "sqlalchemy.engine",
        "python_multipart.multipart",
    ]
    for noisy_logger_name in noisy_loggers:
        noisy_logger = logging.getLogger(noisy_logger_name)
        noisy_logger.setLevel(logging.ERROR)
        noisy_logger.propagate = False  # Prevent double logging

    # Return module-specific logger
    module_logger = logging.getLogger(module_name or __name__)
    module_logger.info(f"Logging initialized for {module_name or __name__} at level {LOG_LEVEL}")

    return module_logger
