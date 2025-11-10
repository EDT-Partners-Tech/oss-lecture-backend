# © [2025] EDT&Partners. Licensed under CC BY 4.0.

import pytest
from utility.prompt_utility import (
    get_question_format,
    build_prompt_document,
    build_prompt_agent,
    clean_document_for_prompt,
    build_reload_prompt,
    build_relevance_prompt,
    build_key_points_prompt,
    build_summary_prompt,
    build_text_processing_prompt
)

class TestGetQuestionFormat:
    def test_get_question_format(self):
        """Test that get_question_format returns a non-empty string."""
        result = get_question_format()
        assert isinstance(result, str)
        assert len(result) > 0
        assert "question" in result
        assert "type" in result
        assert "options" in result
        assert "mcq" in result
        assert "tf" in result
        assert "open" in result


class TestBuildPromptDocument:
    def test_basic_prompt(self):
        """Test building a basic document prompt."""
        result = build_prompt_document(2, 2, 2, "Source text for testing")
        assert isinstance(result, str)
        assert "Generate 6 exam questions" in result
        assert "2 True/False questions" in result
        assert "2 Multiple Choice questions" in result
        assert "2 Open-ended questions" in result
        assert "Source text for testing" in result
        
    def test_with_custom_instructions(self):
        """Test building a prompt with custom instructions."""
        result = build_prompt_document(1, 1, 1, "Source text", "Make it challenging")
        assert "Additional requirements: Make it challenging" in result
        
    def test_with_empty_source(self):
        """Test building a prompt with empty source text."""
        result = build_prompt_document(1, 1, 1, "")
        assert isinstance(result, str)
        assert "Generate 3 exam questions" in result
        
    def test_with_large_numbers(self):
        """Test building a prompt with large numbers of questions."""
        result = build_prompt_document(10, 15, 20, "Source text")
        assert "Generate 45 exam questions" in result
        assert "15 True/False questions" in result
        assert "10 Multiple Choice questions" in result
        assert "20 Open-ended questions" in result


class TestBuildPromptAgent:
    def test_basic_agent_prompt(self):
        """Test building a basic agent prompt."""
        result = build_prompt_agent(2, 2, 2)
        assert isinstance(result, str)
        assert "Generate 6 exam questions" in result
        assert "2 True/False questions" in result
        assert "2 Multiple Choice questions" in result
        assert "2 Open-ended questions" in result
        
    def test_with_custom_instructions(self):
        """Test building an agent prompt with custom instructions."""
        result = build_prompt_agent(1, 1, 1, "Focus on chapter 3")
        assert "<user_question>" in result
        assert "Focus on chapter 3" in result
        
    def test_with_language_specified(self):
        """Test building an agent prompt with a specific language."""
        result = build_prompt_agent(1, 1, 1, "", "", "Spanish")
        assert " to Spanish." in result
        
    def test_with_existing_questions(self):
        """Test building an agent prompt with existing questions to avoid."""
        result = build_prompt_agent(1, 1, 1, "", "Question 1? Question 2?")
        assert "<existing_questions>" in result
        assert "Question 1? Question 2?" in result
        assert "generate questions different from" in result.lower()
        
    def test_with_all_parameters(self):
        """Test building an agent prompt with all parameters filled."""
        result = build_prompt_agent(1, 2, 3, "Focus on ecology", "Previous question about animals", "French")
        assert "Generate 6 exam questions" in result
        assert "1 True/False" in result
        assert "2 Multiple Choice" in result
        assert "3 Open-ended" in result
        assert "Focus on ecology" in result
        assert "Previous question about animals" in result
        assert " to French." in result


class TestCleanDocumentForPrompt:
    def test_basic_cleaning(self):
        """Test basic text cleaning."""
        result = clean_document_for_prompt("Line 1\nLine 2\nLine 3")
        assert result == "Line 1 Line 2 Line 3"
        
    def test_with_empty_string(self):
        """Test cleaning an empty string."""
        result = clean_document_for_prompt("")
        assert result == ""
        
    def test_with_whitespace_only(self):
        """Test cleaning a string with only whitespace."""
        result = clean_document_for_prompt("   \n   \n   ")
        assert result == ""
        
    def test_with_multiple_newlines(self):
        """Test cleaning text with multiple consecutive newlines."""
        result = clean_document_for_prompt("Line 1\n\n\nLine 2")
        assert result == "Line 1   Line 2"
        
    def test_with_leading_trailing_whitespace(self):
        """Test cleaning text with leading and trailing whitespace."""
        result = clean_document_for_prompt("  \n  Text  \n  ")
        assert result == "Text"


class TestBuildReloadPrompt:
    def test_basic_reload_prompt(self):
        """Test building a basic reload prompt."""
        question_data = {
            "type": "mcq",
            "question": "What is the capital of France?",
            "options": ["Paris", "London", "Berlin", "Madrid"],
            "correct_answer": "Paris"
        }
        result = build_reload_prompt(question_data, "Make it harder")
        assert isinstance(result, str)
        assert "What is the capital of France?" in result
        assert "Make it harder" in result
        assert "search_results" in result
        
    def test_with_complex_question_data(self):
        """Test building a reload prompt with complex question data."""
        question_data = {
            "type": "tf",
            "question": "The Earth is flat.",
            "options": ["True", "False"],
            "correct_answer": "False",
            "reason": "Scientific evidence proves the Earth is approximately spherical."
        }
        result = build_reload_prompt(question_data, "Use more advanced concepts")
        assert "The Earth is flat." in result
        assert "Scientific evidence proves" in result
        assert "Use more advanced concepts" in result


class TestBuildRelevancePrompt:
    def test_basic_relevance_prompt(self):
        """Test building a basic relevance prompt."""
        result = build_relevance_prompt("Focus on renewable energy")
        assert isinstance(result, str)
        assert "Rewrite the response" in result
        assert "Focus on renewable energy" in result
        assert "<instructions>" in result
        
    def test_with_complex_instructions(self):
        """Test building a relevance prompt with complex instructions."""
        instructions = "Address the impact of climate change on agriculture and propose solutions"
        result = build_relevance_prompt(instructions)
        assert instructions in result


class TestBuildKeyPointsPrompt:
    def test_basic_key_points_prompt(self):
        """Test building a basic key points prompt."""
        result = build_key_points_prompt("A lengthy academic article about quantum physics")
        assert isinstance(result, str)
        assert "Extract the key points" in result
        assert "A lengthy academic article about quantum physics" in result
        assert "<instructions>" in result
        
    def test_with_empty_source(self):
        """Test building a key points prompt with empty source text."""
        result = build_key_points_prompt("")
        assert "Extract the key points" in result


class TestBuildSummaryPrompt:
    def test_basic_summary_prompt(self):
        """Test building a basic summary prompt."""
        result = build_summary_prompt("This is a transcript to summarize.", "English")
        assert isinstance(result, str)
        assert "summarize the following transcript" in result
        assert "This is a transcript to summarize." in result
        assert "Provide the summary and action points in English" in result
        
    def test_with_different_language(self):
        """Test building a summary prompt with a different language."""
        result = build_summary_prompt("Transcript text", "Spanish")
        assert "Provide the summary and action points in Spanish" in result
        
    def test_with_empty_transcript(self):
        """Test building a summary prompt with an empty transcript."""
        result = build_summary_prompt("", "English")
        assert "summarize the following transcript" in result
        # Even if transcript is empty, the prompt should be formed correctly


class TestBuildTextProcessingPrompt:
    def test_basic_summarize_prompt(self):
        """Test building a basic text processing prompt for summarization."""
        result = build_text_processing_prompt("summarize", ["formal"], ["technical"], "Text to summarize")
        assert isinstance(result, str)
        assert "Summarize this text" in result
        assert "with a formal tone" in result
        assert "for technical audience" in result
        assert "Text to summarize" in result
        assert "<response></response>" in result
        
    def test_expand_with_multiple_tones(self):
        """Test building a prompt for expansion with multiple tones."""
        result = build_text_processing_prompt("expand", ["casual", "friendly"], ["general"], "Short text")
        assert "Expand on this text" in result
        assert "with a casual, friendly tone" in result
        assert "for general audience" in result
        
    def test_rephrase_with_no_tones_or_audiences(self):
        """Test building a prompt for rephrasing with no tones or audiences."""
        result = build_text_processing_prompt("rephrase", [], [], "Text to rephrase")
        assert "Rephrase this text" in result
        assert "tone" not in result
        assert "audience" not in result
        
    def test_format_with_selected_text(self):
        """Test building a prompt for formatting with selected text."""
        result = build_text_processing_prompt(
            "format", ["professional"], ["academic"], 
            "Full document context", "Selected portion"
        )
        assert "Format this text" in result
        assert "with a professional tone" in result
        assert "for academic audience" in result
        assert "Full text: \"Full document context\"" in result
        assert "Selected text: \"Selected portion\"" in result
        
    def test_missing_action(self):
        """Test error handling when an invalid action is provided."""
        # Define a valid set of actions based on the function implementation
        valid_actions = ["summarize", "expand", "rephrase", "format"]
        
        # Test with an action not in the dictionary
        # This should not raise an exception but handle it gracefully
        # In a real application, we might want to add validation to the function
        with pytest.raises(KeyError):
            build_text_processing_prompt("invalid_action", [], [], "Some text")
