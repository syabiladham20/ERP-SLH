with open('app/__init__.py', 'r') as f:
    content = f.read()

# Make sure root logger also gets the handler since other modules use standard logging
replacement = """    import logging
    from logging.handlers import RotatingFileHandler
    if not os.path.exists('logs'):
        os.mkdir('logs')
    file_handler = RotatingFileHandler('logs/erp_slh.log', maxBytes=102400, backupCount=10)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)

    # Configure root logger
    logging.getLogger().addHandler(file_handler)
    logging.getLogger().setLevel(logging.INFO)

    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('ERP SLH startup')"""

content = content.replace("    import logging\n    from logging.handlers import RotatingFileHandler\n    if not os.path.exists('logs'):\n        os.mkdir('logs')\n    file_handler = RotatingFileHandler('logs/erp_slh.log', maxBytes=102400, backupCount=10)\n    file_handler.setFormatter(logging.Formatter(\n        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'\n    ))\n    file_handler.setLevel(logging.INFO)\n    app.logger.addHandler(file_handler)\n    app.logger.setLevel(logging.INFO)\n    app.logger.info('ERP SLH startup')", replacement)

with open('app/__init__.py', 'w') as f:
    f.write(content)
