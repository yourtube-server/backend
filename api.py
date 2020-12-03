from flask import Flask
from flask import request, jsonify
from flask_cors import CORS, cross_origin
from flask_executor import Executor
import json
import time
import uuid
import os
import youtube_dl
import requests 
import shutil
from ffmpy import FFmpeg

app = Flask(__name__)
app.config["DEBUG"] = True
app.config['CORS_HEADERS'] = 'Content-Type'
executor = Executor(app)
CORS(app, resources={r"/*": {"origins": "*"}})

# endpoint to check if an account has been created (we only allow for one accout)


@app.route('/auth/exists', methods=['GET'])
def exists():
	exists = os.path.exists("credentials.txt")
	# check for existience of password file
	response = jsonify({'data': {'account_created': exists}}), 200
	return response

# endpoint to create account (stores username / password combo in plaintext, sue me)


@app.route('/auth/signup', methods=['POST'])
def signup():
	email = request.json['email']
	password = request.json['password']
	with open('credentials.txt', 'w') as file:
		file.write("{}:{}".format(email, password))

	response = jsonify({'data': {'user': {'email' :request.json['email']} } }), 200
	return response

# endpoint to log into account (creates an access token and returns it)
@app.route('/auth/signin', methods=['POST'])
def signin():
	exists = os.path.exists("credentials.txt")
	if not exists:
		response = jsonify({'status': 'error', 'code': 'auth/missing user', 'message': 'There is no user account.'  }), 200
		return response
	else:
		email = request.json['email']
		password = request.json['password']
		with open('credentials.txt', 'r') as file:
			data = file.read()
		e, pw = data.split(':')
		success = (e.lower() == email.lower()) and (pw == password)
		if not success:
			response = jsonify({'status': 'error', 'code': 'auth/invalid credentials', 'message': 'The email/password combo is incorrect.'  }), 200
			return response

	response = jsonify({'data': {'user': {'email' :request.json['email']} } }), 200
	return response

##################################

# # endpoint to scrape videos and store them (store metadata in a db, files directly on the filesystem)
@app.route('/api/scrape', methods=['POST'])
def scrap_video():
	link = request.json['link']

	try:
		with youtube_dl.YoutubeDL({}) as ydl:
			info_dict = ydl.extract_info(link, download=False) 
	except Exception as e:
		response = jsonify({'status': 'error', 'code': 'scrape/invalid link', 'message': 'Error processing video link.'  }), 200
		return response

	executor.submit(download_video(link))
	response = jsonify({'data': {'link': link }}), 200
	return response
	 
def download_video(link):
	identifier = str(uuid.uuid4())
	ydl_opts = {
		'format': 'bestaudio/best',
		'outtmpl': os.getcwd() + '/static/' + identifier + '/' + '%(title)s.%(ext)s',
		'noplaylist': True
	}
	with youtube_dl.YoutubeDL(ydl_opts) as ydl:
		info_dict = ydl.extract_info(link, download=True) 

	# Download the thumbnail
	thumbnail_url = info_dict['thumbnail']
	thumbnail_filename = thumbnail_url.split("/")[-1]
	thumbnail_filepath = os.getcwd() + '/static/' + identifier + '/' + thumbnail_filename
	r = requests.get(thumbnail_url, stream = True)
	if r.status_code == 200:
	# Set decode_content value to True, otherwise the downloaded image file's size will be zero.
		r.raw.decode_content = True 
		with open(thumbnail_filepath, 'wb') as file:
			shutil.copyfileobj(r.raw, file)

	# use ffmpeg to create previews (for use in the scrubber)
	previews_filepath = os.getcwd() + '/static/' + identifier + '/previews/' 
	os.mkdir(previews_filepath)
	video = os.getcwd() + '/static/{}/{}.{}'.format(identifier, info_dict['title'], info_dict['ext'])
	ff = FFmpeg(inputs={video: None}, outputs={previews_filepath + "img%03d.png": ['-vf', 'fps=1/20']})
	ff.run()


	metadata = {}
	metadata['title'] = info_dict['title']
	metadata['filename'] = '/static/{}/{}.{}'.format(identifier, info_dict['title'], info_dict['ext'])
	metadata['duration'] = info_dict['duration']
	metadata['thumbnail'] = thumbnail_filepath
	metadata['previews'] = ['/static/' + identifier + '/previews/'  + f.name for f in os.scandir(previews_filepath) if f.is_file()]


	metadata_filepath = os.getcwd() + '/static/' + identifier + '/metadata.txt'
	with open(metadata_filepath, 'w') as file:
		json.dump(metadata, file)


# # endpoint to get list of all files 
@app.route('/api/videos', methods=['GET'])
def get_videos():
	video_dirs = [os.getcwd() + '/static/' + f.name for f in os.scandir(os.getcwd() + '/static/') if f.is_dir()]
	videos = []
	for video_dir in video_dirs:
		with open(video_dir + '/metadata.txt') as file:
			metadata = json.load(file)
		videos.append(metadata)
	response = jsonify({'data': {'videos': videos}}), 200
	return response

app.run()
