1. **Create the Database Model for Notes**
   - Add `class FloatingNote(db.Model):` in `app.py`.
   - Fields: `id`, `flock_id` (ForeignKey), `chart_id` (String: e.g. "generalChart", "waterChart"), `x_value` (String, e.g. date), `y_value` (Float), `content` (String/Text).
   - Generate database migration (`flask db migrate -m "add floating notes"`, `flask db upgrade` or create an alembic script). Wait, memory says: "All database code (models, migrations, raw SQL) must be dialect-agnostic... Alembic autogenerate may incorrectly flag existing tables like 'weekly_data' for deletion. Always manually review and clean up generated migration scripts before running flask db upgrade." So I will be careful with migration.

2. **Backend API endpoints**
   - GET `/api/floating_notes/<int:flock_id>`: returns all notes for a flock, grouped by chart_id or just a list.
   - POST `/api/floating_notes`: creates a new floating note. Returns the note's id.
   - DELETE `/api/floating_notes/<int:note_id>`: deletes a specific note.

3. **Frontend changes (`flock_detail_modern.html` and `flock_detail_readonly.html`)**
   - Add `<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@2.1.0/dist/chartjs-plugin-annotation.min.js"></script>` after ChartJS imports.
   - Register the annotation plugin: `Chart.register(chartjsPluginAnnotation);`. (Wait, ChartJS Annotation is registered automatically if imported via script tag or we can do `Chart.register(window['chartjs-plugin-annotation'])`).
   - For all charts on these pages (General, Water, Feed, Temp, BW, Male/Female, Hatching, Target), update the UI header controls to include an "Add Note" button. Wait, since there are many charts, a small pencil icon button or similar. I'll add a simple button next to the "Full Screen" and "Toggle Labels" buttons in the chart headers.
   - Add logic for "Add Note mode": clicking the button toggles a boolean `isAddNoteMode[chartId]`. When true, clicking the chart calculates the X and Y coordinates (using `chart.scales.x.getValueForPixel` and `chart.scales.y.getValueForPixel`). Then prompts the user for the text, sends a POST to `/api/floating_notes`, and then reloads/adds the annotation to the specific chart instance and calls `chart.update()`.
   - When fetching notes on page load, apply them to the `plugins.annotation.annotations` object of the respective chart configurations before or after instantiating `new Chart()`.
   - To make them visible text boxes without borders:
     ```json
     {
        type: 'label',
        xValue: date, // or x index if timescale is categorical
        yValue: yValue,
        content: text,
        backgroundColor: 'rgba(255, 255, 255, 0.8)',
        color: 'black',
        borderWidth: 0,
        font: { size: 12 }
     }
     ```
   - Make notes deletable (e.g., clicking the note itself while NOT in add mode asks to delete, or right click, or when clicked we prompt "Delete note?"). We need a simple UI for this. A double-click or click event handled by `chartjs-plugin-annotation` `click` hook.

4. **Complete pre commit steps**
   - Run pre-commit instructions, ensure all verifies pass.
   - Check if database and UI load correctly.

5. **Submit**
   - Commit and submit the code.
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
