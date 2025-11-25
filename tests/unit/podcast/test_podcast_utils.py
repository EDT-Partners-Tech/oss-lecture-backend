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
