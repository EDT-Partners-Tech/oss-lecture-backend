# © [2025] EDT&Partners. Licensed under CC BY 4.0.

from langchain.prompts import PromptTemplate
from function.podcast_generator.utils import PodcastUtils, SupportedPodcastLanguage

def test_get_podcast_prompt_template():
    template = PodcastUtils.get_podcast_prompt_template()
    assert isinstance(template, PromptTemplate)
    assert set(template.input_variables) == {"text", "speakers", "language"}
    # Check that the template contains key markers.
    assert "Human:" in template.template

def test_get_podcast_image_prompt_template():
    template = PodcastUtils.get_podcast_image_prompt_template()
    assert isinstance(template, PromptTemplate)
    assert set(template.input_variables) == {"transcript"}
    # Check that the template instructs to wrap prompt output.
    assert "wrap" in template.template.lower()

def test_get_speakers_english():
    speakers = PodcastUtils.get_speakers(SupportedPodcastLanguage.ENGLISH)
    names = speakers.get_names()
    expected = ["Joanna", "Matthew", "Danielle", "Ruth", "Stephen"]
    for name in expected:
        assert name in names

def test_get_speakers_spanish():
    speakers = PodcastUtils.get_speakers(SupportedPodcastLanguage.SPANISH)
    names = speakers.get_names()
    expected = ["Sergio", "Lucia"]
    for name in expected:
        assert name in names

def test_get_language_code():
    assert PodcastUtils.get_language_code(SupportedPodcastLanguage.ENGLISH) == "en-US"
    assert PodcastUtils.get_language_code(SupportedPodcastLanguage.SPANISH) == "es-ES"
