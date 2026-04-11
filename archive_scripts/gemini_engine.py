import os
import json
from google import genai
from google.genai import types
from privacy_filter import privacy_filter

class GeminiEngine:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")
        self.client = genai.Client(api_key=self.api_key)
        self.model = "gemini-2.5-flash-lite"
        self.system_instruction = (
            "You are a senior poultry breeder consultant. You will receive anonymized production data. "
            "Your goal is to spot mortality spikes, feed efficiency drops, or egg production anomalies "
            "and provide 3 actionable management steps."
        )

    def analyze_flock_data(self, house_name, log_data):
        """
        Receives raw flock logs, anonymizes them, and queries Gemini.
        Returns the deanonymized text response.
        """
        if not log_data:
            return "No data available for analysis."

        # Check data length
        data_len = len(log_data)
        prefix = ""
        if data_len < 14:
            prefix = f"Note: Analysis based on a limited {data_len}-day sample.\n\n"

        # Pass through Privacy Filter
        anonymized_payload = privacy_filter.anonymize_data(log_data, house_name)

        # Convert to JSON string for the prompt
        json_data = json.dumps(anonymized_payload, indent=2)

        prompt = f"Please analyze the following anonymized poultry production data:\n\n{json_data}"

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    temperature=0.3, # Keep it professional and analytical
                )
            )

            raw_response = response.text

            # Pass through Privacy Filter to restore real names
            deanonymized_response = privacy_filter.deanonymize_text(raw_response)

            return f"{prefix}{deanonymized_response}"

        except Exception as e:
            # We don't want to expose raw errors to the UI
            import logging
            logging.error(f"Gemini API Error: {str(e)}")
            raise Exception("The AI Consultant is currently offline. Please try again in an hour.")

# Singleton instance
try:
    gemini_engine = GeminiEngine()
except ValueError as e:
    import logging
    logging.warning(f"Failed to initialize Gemini Engine: {e}")
    gemini_engine = None
