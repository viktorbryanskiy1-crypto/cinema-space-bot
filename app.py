from flask import Flask, render_template
import os

app = Flask(__name__)

@app.route('/')
def index():
    return "<h1>🌌 КиноВселенная работает!</h1><p>Скоро здесь будет космическое приложение</p>"

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
