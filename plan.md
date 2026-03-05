1. **Remove `google-generativeai` and `google-genai` from `requirements.txt`**:
   - Read `requirements.txt`.
   - Remove any mention of `google-generativeai` and `google-genai`.
2. **Uninstall the packages**:
   - Run `pip uninstall -y google-generativeai google-genai`.
3. **Update `app.py` with the new Lite AI functionality**:
   - Implement `get_gemini_lite_response(user_prompt)`.
   - Update the `/api/chat` route to use `get_gemini_lite_response` and handle a missing API key as per user instructions.
4. **Complete Pre-commit Steps**:
   - Call `pre_commit_instructions` tool to run and handle checks.
5. **Submit**:
   - Submit changes.
