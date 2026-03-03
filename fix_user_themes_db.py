import app

def fix_themes():
    with app.app.app_context():
        users = app.User.query.all()
        for user in users:
            user.theme = 'base_tabler.html'
        app.db.session.commit()
        print("Updated existing user themes to base_tabler.html")

if __name__ == '__main__':
    fix_themes()
