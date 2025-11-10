# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import asyncio
import random
from functools import wraps
from botocore.exceptions import ClientError

class RetryWithExponentialBackoff:
    """
    A decorator that implements exponential backoff with jitter for retrying operations
    that fail due to AWS throttling or other transient errors.
    
    Args:
        max_retries (int): Maximum number of retry attempts
        initial_delay (int): Initial delay between retries in seconds
        max_delay (int): Maximum delay between retries in seconds
    """
    def __init__(self, max_retries=5, initial_delay=1, max_delay=32):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay

    def __call__(self, func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            delay = self.initial_delay
            attempt = 0
            last_exception = None
            
            while attempt < self.max_retries:
                try:
                    result = await func(*args, **kwargs)
                    # Check if the result indicates a failure
                    if isinstance(result, str) and "Unable to generate response" in result:
                        raise Exception("Bedrock API failed to generate response")
                    return result
                except (ClientError, Exception) as e:
                    should_retry = False
                    error_message = str(e)

                    if isinstance(e, ClientError):
                        # Check for throttling
                        if e.response['Error']['Code'] == 'ThrottlingException':
                            should_retry = True
                            error_message = "AWS API throttling"
                    elif "Unable to generate response" in str(e):
                        # Retry on Bedrock API failures
                        should_retry = True
                        error_message = "Bedrock API failure"

                    if should_retry:
                        last_exception = e
                        attempt += 1
                        
                        if attempt == self.max_retries:
                            print(f"Max retries ({self.max_retries}) reached. Last error: {error_message}")
                            raise
                        
                        # Calculate delay with exponential backoff and jitter
                        jitter = random.uniform(0, 0.1 * delay)
                        sleep_time = min(delay + jitter, self.max_delay)
                        
                        print(f"{error_message}. Retrying in {sleep_time:.2f} seconds... (Attempt {attempt}/{self.max_retries})")
                        await asyncio.sleep(sleep_time)
                        delay *= 2  # Exponential backoff
                    else:
                        # If it's not a retryable error, raise it immediately
                        raise
            
            raise last_exception
        return wrapper 