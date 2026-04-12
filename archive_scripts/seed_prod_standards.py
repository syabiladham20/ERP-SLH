from app import app, db, Standard

PRODUCTION_STANDARDS = { 1: {"age_days": 175, "hen_week_pct": 5.4, "egg_weight_g": 50.2, "hatch_pct": 78.0, "cum_eggs_hha": 0.4, "cum_chicks_hha": 0.0}, 2: {"age_days": 182, "hen_week_pct": 25.0, "egg_weight_g": 51.9, "hatch_pct": 80.4, "cum_eggs_hha": 2.1, "cum_chicks_hha": 1.0}, 3: {"age_days": 189, "hen_week_pct": 55.3, "egg_weight_g": 53.6, "hatch_pct": 82.2, "cum_eggs_hha": 6.0, "cum_chicks_hha": 3.8}, 4: {"age_days": 196, "hen_week_pct": 77.0, "egg_weight_g": 55.2, "hatch_pct": 83.6, "cum_eggs_hha": 11.3, "cum_chicks_hha": 7.8}, 5: {"age_days": 203, "hen_week_pct": 85.8, "egg_weight_g": 56.5, "hatch_pct": 84.7, "cum_eggs_hha": 17.3, "cum_chicks_hha": 12.6}, 6: {"age_days": 210, "hen_week_pct": 88.9, "egg_weight_g": 57.6, "hatch_pct": 85.5, "cum_eggs_hha": 23.4, "cum_chicks_hha": 17.7}, 7: {"age_days": 217, "hen_week_pct": 89.8, "egg_weight_g": 58.6, "hatch_pct": 86.3, "cum_eggs_hha": 29.6, "cum_chicks_hha": 23.0}, 8: {"age_days": 224, "hen_week_pct": 89.2, "egg_weight_g": 59.5, "hatch_pct": 86.8, "cum_eggs_hha": 35.7, "cum_chicks_hha": 28.3}, 9: {"age_days": 231, "hen_week_pct": 88.2, "egg_weight_g": 60.2, "hatch_pct": 87.3, "cum_eggs_hha": 41.8, "cum_chicks_hha": 33.6}, 10: {"age_days": 238, "hen_week_pct": 87.2, "egg_weight_g": 60.9, "hatch_pct": 87.7, "cum_eggs_hha": 47.8, "cum_chicks_hha": 38.8}, 11: {"age_days": 245, "hen_week_pct": 86.3, "egg_weight_g": 61.5, "hatch_pct": 88.0, "cum_eggs_hha": 53.7, "cum_chicks_hha": 44.0}, 12: {"age_days": 252, "hen_week_pct": 85.3, "egg_weight_g": 62.1, "hatch_pct": 88.3, "cum_eggs_hha": 59.5, "cum_chicks_hha": 49.1}, 13: {"age_days": 259, "hen_week_pct": 84.3, "egg_weight_g": 62.6, "hatch_pct": 88.4, "cum_eggs_hha": 65.3, "cum_chicks_hha": 54.1}, 14: {"age_days": 266, "hen_week_pct": 83.3, "egg_weight_g": 63.1, "hatch_pct": 88.6, "cum_eggs_hha": 70.9, "cum_chicks_hha": 59.0}, 15: {"age_days": 273, "hen_week_pct": 82.3, "egg_weight_g": 63.5, "hatch_pct": 88.7, "cum_eggs_hha": 76.5, "cum_chicks_hha": 63.9}, 16: {"age_days": 280, "hen_week_pct": 81.1, "egg_weight_g": 64.0, "hatch_pct": 88.7, "cum_eggs_hha": 82.0, "cum_chicks_hha": 68.7}, 17: {"age_days": 287, "hen_week_pct": 80.1, "egg_weight_g": 64.4, "hatch_pct": 88.8, "cum_eggs_hha": 87.4, "cum_chicks_hha": 73.4}, 18: {"age_days": 294, "hen_week_pct": 79.1, "egg_weight_g": 64.8, "hatch_pct": 88.8, "cum_eggs_hha": 92.8, "cum_chicks_hha": 77.9}, 19: {"age_days": 301, "hen_week_pct": 78.0, "egg_weight_g": 65.3, "hatch_pct": 88.8, "cum_eggs_hha": 98.0, "cum_chicks_hha": 82.4}, 20: {"age_days": 308, "hen_week_pct": 77.0, "egg_weight_g": 65.7, "hatch_pct": 88.7, "cum_eggs_hha": 103.2, "cum_chicks_hha": 86.8}, 21: {"age_days": 315, "hen_week_pct": 76.0, "egg_weight_g": 66.1, "hatch_pct": 88.6, "cum_eggs_hha": 108.3, "cum_chicks_hha": 91.1}, 22: {"age_days": 322, "hen_week_pct": 74.9, "egg_weight_g": 66.5, "hatch_pct": 88.6, "cum_eggs_hha": 113.3, "cum_chicks_hha": 95.3}, 23: {"age_days": 329, "hen_week_pct": 73.9, "egg_weight_g": 66.9, "hatch_pct": 88.5, "cum_eggs_hha": 118.2, "cum_chicks_hha": 99.4}, 24: {"age_days": 336, "hen_week_pct": 72.7, "egg_weight_g": 67.3, "hatch_pct": 88.3, "cum_eggs_hha": 123.1, "cum_chicks_hha": 103.4}, 25: {"age_days": 343, "hen_week_pct": 71.7, "egg_weight_g": 67.7, "hatch_pct": 88.2, "cum_eggs_hha": 127.8, "cum_chicks_hha": 107.3}, 26: {"age_days": 350, "hen_week_pct": 70.6, "egg_weight_g": 68.0, "hatch_pct": 88.1, "cum_eggs_hha": 132.5, "cum_chicks_hha": 111.1}, 27: {"age_days": 357, "hen_week_pct": 69.5, "egg_weight_g": 68.4, "hatch_pct": 87.9, "cum_eggs_hha": 137.1, "cum_chicks_hha": 114.9}, 28: {"age_days": 364, "hen_week_pct": 68.5, "egg_weight_g": 68.7, "hatch_pct": 87.8, "cum_eggs_hha": 141.7, "cum_chicks_hha": 118.5}, 29: {"age_days": 371, "hen_week_pct": 67.4, "egg_weight_g": 69.0, "hatch_pct": 87.6, "cum_eggs_hha": 146.1, "cum_chicks_hha": 122.0}, 30: {"age_days": 378, "hen_week_pct": 66.3, "egg_weight_g": 69.3, "hatch_pct": 87.4, "cum_eggs_hha": 150.5, "cum_chicks_hha": 125.4}, 31: {"age_days": 385, "hen_week_pct": 65.3, "egg_weight_g": 69.5, "hatch_pct": 87.2, "cum_eggs_hha": 154.8, "cum_chicks_hha": 128.8}, 32: {"age_days": 392, "hen_week_pct": 64.0, "egg_weight_g": 69.8, "hatch_pct": 87.1, "cum_eggs_hha": 159.0, "cum_chicks_hha": 132.0}, 33: {"age_days": 399, "hen_week_pct": 62.9, "egg_weight_g": 70.0, "hatch_pct": 86.9, "cum_eggs_hha": 163.1, "cum_chicks_hha": 135.2}, 34: {"age_days": 406, "hen_week_pct": 61.8, "egg_weight_g": 70.2, "hatch_pct": 86.7, "cum_eggs_hha": 167.1, "cum_chicks_hha": 138.2}, 35: {"age_days": 413, "hen_week_pct": 60.8, "egg_weight_g": 70.3, "hatch_pct": 86.5, "cum_eggs_hha": 171.1, "cum_chicks_hha": 141.2}, 36: {"age_days": 420, "hen_week_pct": 59.7, "egg_weight_g": 70.5, "hatch_pct": 86.2, "cum_eggs_hha": 174.9, "cum_chicks_hha": 144.0}, 37: {"age_days": 427, "hen_week_pct": 58.5, "egg_weight_g": 70.7, "hatch_pct": 86.0, "cum_eggs_hha": 178.7, "cum_chicks_hha": 146.8}, 38: {"age_days": 434, "hen_week_pct": 57.4, "egg_weight_g": 70.8, "hatch_pct": 85.8, "cum_eggs_hha": 182.4, "cum_chicks_hha": 149.5}, 39: {"age_days": 441, "hen_week_pct": 56.3, "egg_weight_g": 71.0, "hatch_pct": 85.6, "cum_eggs_hha": 186.1, "cum_chicks_hha": 152.1}, 40: {"age_days": 448, "hen_week_pct": 55.0, "age_wks": 64, "egg_weight_g": 71.2, "hatch_pct": 85.6, "cum_eggs_hha": 189.6, "cum_chicks_hha": 154.6} }

def seed_prod_standards():
    with app.app_context():
        count = 0
        for prod_week, data in PRODUCTION_STANDARDS.items():
            # Week 1 of Production = Chronological Age Week 25
            bio_week = prod_week + 24

            s = Standard.query.filter_by(week=bio_week).first()
            if not s:
                s = Standard(week=bio_week)
                db.session.add(s)

            s.production_week = prod_week
            s.std_cum_eggs_hha = data.get('cum_eggs_hha', 0.0)
            s.std_cum_chicks_hha = data.get('cum_chicks_hha', 0.0)

            # Update other metrics if present in dict
            if 'hen_week_pct' in data:
                s.std_egg_prod = data['hen_week_pct']
            if 'egg_weight_g' in data:
                s.std_egg_weight = data['egg_weight_g']
            if 'hatch_pct' in data:
                s.std_hatchability = data['hatch_pct']

            count += 1

        db.session.commit()
        print(f"Seeded {count} production standards.")

if __name__ == "__main__":
    seed_prod_standards()
