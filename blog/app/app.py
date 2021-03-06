import datetime
import functools
import os
import re
import urllib


from flask import ( Flask , abort , flash ,Markup , redirect , render_template , request , Response , session , url_for)
from markdown import markdown
from markdown.extensions.codehilite import CodeHiliteExtension
from markdown.extensions.extra import ExtraExtension
from micawber import bootstrap_basic , parse_html
from micawber.cache import Cache as OEmbedCache
from peewee import *
from playhouse.flask_utils import FlaskDB , get_object_or_404 , object_list
from playhouse.sqlite_ext import *

ADMIN_PASSWORD = 'secret' #1) Implement one way hash to store password
APP_DIR = os.path.dirname(os.path.realpath(__file__))
DATABASE = 'sqliteext:///%s' % os.path.join(APP_DIR , 'blog.db')
DEBUG = False
SECRET_KEY = 'shhh, secret'
SITE_WIDTH = 800

app = Flask(__name__)
app.config.from_object(__name__)

flask_db = FlaskDB(app)
database = flask_db.database

oembed_providers = bootstrap_basic(OEmbedCache())

class Entry(flask_db.Model):
	title = CharField()
	slug = CharField(unique=True)
	content = TextField()
	published = BooleanField(index=True)
	timestamp = DateTimeField(default=datetime.datetime.now , index = True)

	def save(self, *args , **kwargs):
		if not self.slug:
			self.slug = re.sub('[^\w]+','-',self.title.lower())
		ret = super(Entry , self).save(*args , **kwargs)

		#store search content

		self.update_search_index()
		return ret

	def update_search_index(self):
		search_content = '\n'.join((self.title, self.content))
		try:
			fts_entry = FTSEntry.get(FTSEntry.docid == self.id)
		except FTSEntry.DoesNotExist:
			FTSEntry.create(docid=self.id, content=search_content)
		else:
			fts_entry.content = search_content
			fts_entry.save()

class FTSEntry(FTSModel):
	content = SearchField()

	class Meta: 
		database = database

def login_required(fn):
	@functools.wraps(fn)
	def inner(*args , **kwargs):
		if session.get('logged_in'):
			return fn(*args , **kwargs)
		return redirect(url_for('login', next = request.path))
	return inner


@classmethod
def public(cls):
	return Entry.select().where(Entry.published == True)

@classmethod
def search(cls , query):
	words = [word.strip() for word in query.split() if word.strip()]
	if not words:
		return Entry.select().where(Entry.id == 0)
	else:
		search = ' '.join(words)

	return (Entry
		.select(Entry , FTSEntry.rank().alias('score'))
		.join(FTSEntry, on=(Entry.id == FTSEntry.docid))
		.where(
			(Entry.published == True) &
			(FTSEntry.match(search)))
		.order_by(SQL('score')))

@classmethod
def drafts(cls):
	return Entry.select().where(Entry.publised == False)

@app.route('/login/',methods = ['GET','POST'])
def login():
	next_url = request.args.get('next') or request.form.get('next')
	if request.method == 'POST' and request.form.get('password'):
		password = request.form.get('password')
		if password == app.config['ADMIN_PASSWORD']:
			session['logged_in'] = True
			session.permanent = True
			flash('You are now logged in' , 'success')
			return redirect(next_url or url_for('index'))
		else:
			flash('Incorrect password', 'danger')
	return render_template('login.html' , next_url=next_url)


@app.route('/drafts/')
@login_required
def drafts():
	query = Entry.drafts().order_by(Entry.timestamp.desc())
	return object_list('index.html', query)

@app.route('/<slug>/')
def detail(slug):
	if session.get('logged_in'):
		query = Entry.select()

	else:
		query = Entry.public()
	entry = get_object_or_404(query , Entry.slug == slug)
	return render_template('detail.html', entry=entry)

@app.route('/')
def index():
	search_query = request.args.get('q')
	if search_query:
		query = Entry.search(search_query)
	else:
		query = Entry.public().order_by(Entry.timestamp.desc())
	return object_list('index.html', query , search = search_query)

@app.route('/logout/' , methods=['GET','POST'])
def logout():
	if request.method == 'POST':
		session.clear()
		return redirect(url_for('login'))
	return render_template('logout.html')

@app.template_filter('clean_querystring')
def clean_querystring(request_args , *keys_to_remove , **new_value):
	querystring = dict((key,value) for key,value in request_args.items())
	for key in keys_to_remove:
		querystring.pop(key, None)
	querystring.update(new_value)
	return urllib.urlencode(querystring)


@app.errorhandler(404)
def not_found(exc):
	return Response('<h3>Not Found</h3>')

def main():
	database.create_tables([Entry , FTSEntry])
	app.run(debug=True)

if __name__ == '__main__':
	main()

