import json
import os
import re

MAPPING_FILE = 'ai_identity_map.json'

# Global mappings
FARM_NAME = "Sin Long Heng Breeding Farm"
ANON_FARM_NAME = "Client_Alpha"

class PrivacyFilter:
    def __init__(self, mapping_file=MAPPING_FILE):
        self.mapping_file = mapping_file
        self.mappings = self._load_mappings()

    def _load_mappings(self):
        if os.path.exists(self.mapping_file):
            with open(self.mapping_file, 'r') as f:
                return json.load(f)
        return {
            "houses": {},
            "staff": {},
            "next_house_id": 1,
            "next_staff_id": 1
        }

    def _save_mappings(self):
        with open(self.mapping_file, 'w') as f:
            json.dump(self.mappings, f, indent=4)

    def _get_or_create_house_id(self, house_name):
        if not house_name:
            return None
        if house_name not in self.mappings['houses']:
            new_id = f"Unit_{self.mappings['next_house_id']:02d}"
            self.mappings['houses'][house_name] = new_id
            self.mappings['next_house_id'] += 1
            self._save_mappings()
        return self.mappings['houses'][house_name]

    def _get_or_create_staff_id(self, staff_name):
        if not staff_name:
            return None
        if staff_name not in self.mappings['staff']:
            new_id = f"Supervisor_{self.mappings['next_staff_id']:02d}"
            self.mappings['staff'][staff_name] = new_id
            self.mappings['next_staff_id'] += 1
            self._save_mappings()
        return self.mappings['staff'][staff_name]

    def anonymize_data(self, data_list, house_name):
        """
        Takes a list of dictionary logs and a house name.
        Anonymizes the house name and any staff names in clinical notes.
        """
        anon_house = self._get_or_create_house_id(house_name)

        anonymized_data = []
        for row in data_list:
            anon_row = row.copy()

            # Anonymize clinical notes if they exist
            if 'clinical_notes' in anon_row and anon_row['clinical_notes']:
                notes = anon_row['clinical_notes']
                # Try to extract and replace known staff names if they appear in notes
                for real_name, anon_name in self.mappings['staff'].items():
                    notes = re.sub(r'\b' + re.escape(real_name) + r'\b', anon_name, notes, flags=re.IGNORECASE)

                # Replace the farm name globally
                notes = re.sub(r'\b' + re.escape(FARM_NAME) + r'\b', ANON_FARM_NAME, notes, flags=re.IGNORECASE)
                anon_row['clinical_notes'] = notes

            anonymized_data.append(anon_row)

        return {
            "farm": ANON_FARM_NAME,
            "house": anon_house,
            "logs": anonymized_data
        }

    def deanonymize_text(self, text):
        """
        Reverses the anonymization mappings in the AI's textual response.
        """
        if not text:
            return text

        # Reverse Farm Name
        text = text.replace(ANON_FARM_NAME, FARM_NAME)

        # Reverse Houses
        for real_name, anon_name in self.mappings['houses'].items():
            text = text.replace(anon_name, real_name)

        # Reverse Staff
        for real_name, anon_name in self.mappings['staff'].items():
            text = text.replace(anon_name, real_name)

        return text

# Singleton instance for the app to use
privacy_filter = PrivacyFilter()
