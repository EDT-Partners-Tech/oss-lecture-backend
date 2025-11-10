# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from langchain.prompts import PromptTemplate
from typing import Dict, List
from enum import Enum

CLAUDE_PODCAST_PROMPT_TEMPLATE = """
\n\nHuman: I'd like you to transform the following text into an engaging podcast dialogue. 
The text may be messy or unstructured since it could come from various sources like PDFs or web pages. 
Please focus on extracting and discussing the key insights in a conversational format.

Here's the text to work with:

<source>
{text}
</source>

Please create a natural, entertaining podcast dialogue that:
1. Features 2-3 speakers with distinct personalities and perspectives
2. Explains complex concepts in an accessible way
3. Uses storytelling and real-world examples to illustrate key points
4. Maintains an engaging conversational flow
5. Naturally weaves in key insights from the source material
6. Concludes with an organic summary of the main takeaways

The dialogue should feature not more than 2-3 speakers with the following names and personalities:
{speakers}

The dialogue should feel like a real podcast conversation between knowledgeable but relatable speakers. 
Each speaker should offer unique insights, explain complex ideas in a digestible manner, and create an engaging atmosphere.
The conversation should have a natural flow, with each speaker building on the other's points and providing a clear, cohesive narrative.
Focus on explaining key insights from the source material, making the conversation informative and enjoyable for a general audience.

Please ensure the dialogue:
- Flows smoothly from one point to the next, avoiding awkward pauses or interruptions.
- Uses examples or anecdotes to clarify and emphasize important points.
- Ends with a natural summary of the discussion that reinforces the key takeaways.

The conversation should be ready for audio production, and should feel authentic, as if the audience is listening to a real-time discussion.

Wrap the dialog between backticks like this:
```
dialogue
```

Follow this strict format for the dialogue:
```
Speaker 1: Dialogue text.
Speaker 2: Dialogue text.
...
```

Make sure to include a podcast title before the dialogue following the strict format: 
~ Your podcast title here ~

Generate the output in {language} language.

\n\nAssistant:
"""

CLAUDE_PODCAST_IMAGE_PROMPT_TEMPLATE = """
I have a transcript of a podcast and would like to generate a descriptive image generation prompt based on its content. 
Please analyze the transcript provided and craft a detailed prompt that can be used with image generation AI models like DALL·E or Stable Diffusion. 

The prompt should include:
	1.	A clear description of the key visual elements mentioned in the podcast (e.g., people, objects, landscapes).
	2.	Any specific details about the style, mood, or colors mentioned or implied in the discussion.
	3.	A focus on creating an engaging and visually interesting representation of the podcast’s topic or theme.

The prompt can't be longer than 350 characters and should be detailed enough to guide the creation of a compelling image based on the podcast content.    

Here is the transcript:
{transcript}

Wrap the generated prompt between backticks like this:
```
Your crafted prompt here.
```

\n\nAssistant:
"""

POLLY_ENGLISH_SPEAKERS = [
    {"name": "Joanna", "personality": "Friendly and empathetic, guiding the conversation in a warm and approachable way."},
    {"name": "Matthew", "personality": "Confident and articulate, offering clear explanations and thoughtful insights."},
    {"name": "Danielle", "personality": "Calm and clear, providing deeper insights and maintaining a balanced tone."},
    {"name": "Ruth", "personality": "Energetic and pragmatic, keeping the conversation lively and relatable."},
    {"name": "Stephen", "personality": "Detailed and engaging, explaining points in a clear and interesting way."}
]

POLLY_SPANISH_SPEAKERS = [
    {"name": "Sergio", "personality": "Friendly and empathetic, guiding the conversation in a warm and approachable way."},
    {"name": "Lucia", "personality": "Confident and articulate, offering clear explanations and thoughtful insights."},
]

class Speakers:
    """
    A class to represent a collection of speakers.

    Attributes:
    -----------
    speakers : List[Dict[str, str]]
        A list of dictionaries where each dictionary contains details of a speaker.

    Methods:
    --------
    get_names():
        Returns a list of names of all speakers.

    __str__():
        Returns a string representation of all speakers with their names and personalities.
    """
    def __init__(self, speakers_spec: List[Dict[str, str]]):
        self.speakers_data = speakers_spec

    def get_names(self):
        return [speaker['name'] for speaker in self.speakers_data]

    def __str__(self):
        return "\n".join([f"**{speaker['name']}**: {speaker['personality']}" for speaker in self.speakers_data])


class SupportedPodcastLanguage(str, Enum):
    """
    SupportedPodcastLanguage is an enumeration that represents the languages supported for podcasts.

    Attributes:
        ENGLISH (str): Represents the English language.
        SPANISH (str): Represents the Spanish language.
    """
    ENGLISH = "english"
    SPANISH = "spanish"


POLLY_SPEAKERS: Dict[SupportedPodcastLanguage, Speakers] = {
    SupportedPodcastLanguage.ENGLISH: Speakers(POLLY_ENGLISH_SPEAKERS),
    SupportedPodcastLanguage.SPANISH: Speakers(POLLY_SPANISH_SPEAKERS)
}

LANGUAGE_CODE_MAP: Dict[SupportedPodcastLanguage, str] = {
    SupportedPodcastLanguage.ENGLISH: "en-US",
    SupportedPodcastLanguage.SPANISH: "es-ES"
}

class PodcastUtils:
    """
    A utility class for handling podcast-related operations.

    Methods
    -------
    get_podcast_prompt_template() -> PromptTemplate
        Returns a PromptTemplate object for generating podcast prompts.

    get_podcast_image_prompt_template() -> PromptTemplate
        Returns a PromptTemplate object for generating podcast image prompts.
    
    get_speakers(language: SupportedPodcastLanguage) -> Speakers
        Returns a list of speakers for the given language.
    
    get_language_code(language: SupportedPodcastLanguage) -> str
        Returns the language code for the given language.
    """
    @staticmethod
    def get_podcast_prompt_template() -> PromptTemplate:
        return PromptTemplate(
            input_variables=["text", "speakers", "language"],
            template=CLAUDE_PODCAST_PROMPT_TEMPLATE,
        )
    
    @staticmethod
    def get_podcast_image_prompt_template() -> PromptTemplate:
        return PromptTemplate(
            input_variables=["transcript"],
            template=CLAUDE_PODCAST_IMAGE_PROMPT_TEMPLATE,
        )

    @staticmethod
    def get_speakers(language: SupportedPodcastLanguage) -> Speakers:
        return POLLY_SPEAKERS[language]

    @staticmethod
    def get_language_code(language: SupportedPodcastLanguage) -> str:
        return LANGUAGE_CODE_MAP[language]