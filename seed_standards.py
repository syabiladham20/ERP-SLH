from app import app, seed_standards_from_file

if __name__ == '__main__':
    with app.app_context():
        print("Starting seeding process...")
        success, message = seed_standards_from_file()
        print(message)
