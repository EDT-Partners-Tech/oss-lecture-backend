# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import os
import openai
from typing import Union

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_completion(
    prompt: str,
    system_message: str = "You are a helpful assistant.",
    model: str = "gpt-4o",
    temperature: float = 0.3,
    json_mode: bool = False,
) -> Union[str, dict]:
    """
        Generate a completion using the OpenAI API.

    Args:
        prompt (str): The user's prompt or query.
        system_message (str, optional): The system message to set the context for the assistant.
            Defaults to "You are a helpful assistant.".
        model (str, optional): The name of the OpenAI model to use for generating the completion.
            Defaults to "gpt-4o".
        temperature (float, optional): The sampling temperature for controlling the randomness of the generated text.
            Defaults to 0.3.
        json_mode (bool, optional): Whether to return the response in JSON format.
            Defaults to False.

    Returns:
        Union[str, dict]: The generated completion.
            If json_mode is True, returns the complete API response as a dictionary.
            If json_mode is False, returns the generated text as a string.
    """

    if json_mode:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            top_p=1,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
    else:
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            top_p=1,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content
