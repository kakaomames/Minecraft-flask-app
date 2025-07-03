from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/setting')
def setting():
    return render_template('setting.html')

@app.route('/store')
def store():
    return render_template('store.html')

@app.route('/menu')
def menu():
    return render_template('menu.html')

if __name__ == '__main__':
    app.run(debug=True) # debug=True は開発中に便利ですが、本番環境ではFalseにしてください
