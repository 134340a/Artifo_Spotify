from flask import Flask, render_template, redirect, request, session, make_response,session,redirect
import spotipy
import spotipy.util as util
from spo_credentials import *
import time
import json
import pandas as pd
import threading, webbrowser
from spotipy.oauth2 import SpotifyOAuth
import os


app = Flask(__name__)
app.secret_key = SSK

url = "http://artifo.vercel.app/"
API_BASE = 'https://accounts.spotify.com'

# Make sure you add this to Redirect URIs in the setting of the application dashboard
REDIRECT_URI = "http://artifo.vercel.app/api_callback"

SCOPE = "user-read-recently-played playlist-modify-public playlist-modify-private playlist-read-private playlist-read-collaborative user-follow-read user-library-read"

# Set this to True for testing but you probaly want it set to False in production.
SHOW_DIALOG = True


# display the frontpage
@app.route("/")
def front():
    return render_template('frontpage.html')

# authorization-code-flow Step 1. Have your application request authorization; 
# the user logs in and authorizes access
@app.route("/login")
def verify():
    
    # Don't reuse a SpotifyOAuth object because they store token info and you could leak user tokens if you reuse a SpotifyOAuth object
    sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id = CLI_ID, client_secret = CLI_SEC, 
                                           redirect_uri = REDIRECT_URI, scope = SCOPE)
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

@app.route("/index")
def index(methods=['POST']):
    if request.method == 'post':
        string= request.form("string")
        print(string)
        return redirect('/go')
    else:
        #print('ind.html is rendered')
        return render_template('index.html')### change to ind2

# authorization-code-flow Step 2.
# Have your application request refresh and access tokens;
# Spotify returns access and refresh tokens
@app.route("/api_callback")
def api_callback():
    # Don't reuse a SpotifyOAuth object because they store token info and you could leak user tokens if you reuse a SpotifyOAuth object
    sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id = CLI_ID, client_secret = CLI_SEC, 
                                           redirect_uri = REDIRECT_URI, scope = SCOPE)    
    session.clear()
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)

    # Saving the access token along with all other token related info
    session["token_info"] = token_info


    return redirect("index")

# authorization-code-flow Step 3.
# Use the access token to access the Spotify Web API;
# Spotify returns requested data
@app.route("/go", methods=['POST'])
def go():
    
    global artist_df, playlist_df, artist, track_uri_list

    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    if request.method == "POST":
        inputs = request.form['input']
        artist = inputs.split(',')
        print (artist)
    else:
        return 'incorrect input'
    
    
    # search for the artist uri
    artist_name = []
    artist_uri = []
    for a in artist:
        results = sp.search(q=a, limit=1, type='artist')
        #print(results)
        art = results['artists']['items'][0]
        artist_name.append(art['name'])
        artist_uri.append(art['uri'])
      
    a_df = {'artist':artist_name, 'uri':artist_uri}
    artist_df = pd.DataFrame(a_df)
 
    
    # find from saved tracks
    saved_tracks  = get_saved_tracks()
    saved_tracks_df = pd.DataFrame(saved_tracks)
    # search saved_tracks for artist_focused tracks
    af = saved_tracks_df.loc[saved_tracks_df['track_artists'].str.contains('|'.join(artist_name))]
    # create playlist_df
    playlist_df = pd.DataFrame(columns=['track_name', 'track_uri', 'track_artists', 'track_artists_uri'])
    # add tracks to the playlist df
    playlist_df = playlist_df.append(af)
    html = playlist_df.to_html()

    # find artists from saved albums 
    saved_albums  = get_saved_album()
    saved_albums_df = pd.DataFrame(saved_albums)
    af = saved_albums_df.loc[saved_albums_df['album_artist'].str.contains('|'.join(artist_name))]
    
    album_tracks_df = pd.DataFrame(columns=['track_name', 'track_uri', 'track_artists', 'track_artists_uri'])
    for a in af['album_uri']:
      album_tracks  = get_album_tracks(a)
      df1 = pd.DataFrame(album_tracks)
      album_tracks_df = album_tracks_df.append(df1, ignore_index=True)
     
    # add album tracks from artists to the playlist_df
    playlist_df = playlist_df.append(album_tracks_df).reset_index()
    playlist_df.drop('index', axis=1, inplace=True)
    
    top_tracks_df = pd.DataFrame(columns=['track_name', 'track_uri', 'track_artists', 'track_artists_uri'])
    for a in artist_df['uri']:
      top_tracks  = get_top_tracks(a)
      df1 = pd.DataFrame(top_tracks)
      top_tracks_df = top_tracks_df.append(df1, ignore_index=True)
    
    # add album tracks from artists to the playlist_df
    playlist_df = playlist_df.append(top_tracks_df).reset_index()
   
    # drop index column
    playlist_df.drop('index', axis=1, inplace=True)
    
    # remove duplicates
    playlist_df.drop_duplicates(subset=['track_name'],inplace=True)

    # shuffle playlist_df
    playlist_df = playlist_df.sample(frac=1).reset_index()
    pltracks = playlist_df[['track_name', 'track_artists']].copy()
    
    html = pltracks.to_html()
   
    ## write to playlist.html
    text = '''
    
    
    <html>
       <body>
          <head>
             <title>SPOTIFY PLAYLIST</title>
          </head>
          <p>DO YOU WANT TO SAVE PLAYLIST TO YOUR ACCOUNT?</p>
              <form action="/saved" method="get">
                <button> <a href="/saved">SAVE IT!</a></button>
                <button> <a href="/index">NEVERMIND</a></button>
            </form>
    
          </form>
       </body>
    </html>
    '''

    pl = html + text

    return pl 
    

# Checks to see if token is valid and gets a new token if not
def get_token(session):
    token_valid = False
    token_info = session.get("token_info", {})

    # Checking if the session already has a token stored
    if not (session.get('token_info', False)):
        token_valid = False
        return token_info, token_valid

    # Checking if token has expired
    now = int(time.time())
    is_token_expired = session.get('token_info').get('expires_at') - now < 60

    # Refreshing token if it has expired
    if (is_token_expired):
        # Don't reuse a SpotifyOAuth object because they store token info and you could leak user tokens if you reuse a SpotifyOAuth object
        sp_oauth = spotipy.oauth2.SpotifyOAuth(client_id = CLI_ID, client_secret = CLI_SEC, redirect_uri = REDIRECT_URI, scope = SCOPE)
        token_info = sp_oauth.refresh_access_token(session.get('token_info').get('refresh_token'))

    token_valid = True
    return token_info, token_valid


### function to get the current user's saved tracks (track name, artist, id)
def get_saved_tracks(limit = 50, offset = 0):
    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    saved_tracks = []
       
    # get initial list of tracks to determine length
    saved_tracks_obj = sp.current_user_saved_tracks(limit = limit, offset = offset)
    num_saved_tracks = saved_tracks_obj['total']
    
    # loop through to get all saved tracked
    while (offset < num_saved_tracks):
        saved_tracks_obj = sp.current_user_saved_tracks(limit = limit, offset = offset)
        
        # add track information to running list
        for track_obj in saved_tracks_obj['items']:
            saved_tracks.append({
                'track_name': track_obj['track']['name'],
                'track_uri': track_obj['track']['uri'],
                'track_artists': ', '.join([artist['name'] for artist in track_obj['track']['artists']]),
                'track_artists_uri': ', '.join([artist['uri'] for artist in track_obj['track']['artists']])
            })
            
        offset += limit
        
    return saved_tracks

### function to get the current user's saved album (album name, artist, id)
def get_saved_album(limit = 50, offset = 0):
    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    saved_albums = [ ]
    
    # get initial list of albums to determine length
    saved_albums_obj = sp.current_user_saved_albums(limit = limit, offset = offset)
    num_saved_albums = saved_albums_obj['total']
    
    # loop through to get all saved albums
    while (offset < num_saved_albums):
        saved_albums_obj = sp.current_user_saved_albums(limit = limit, offset = offset)
        
        # add album information to running list
        for album_obj in saved_albums_obj['items']:
            saved_albums.append({
                'album_name': album_obj['album']['name'],
                'album_artist': ', '.join([artist['name'] for artist in album_obj['album']['artists']]),
                'album_uri': album_obj['album']['uri']
            })
            
        offset += limit
        
    return saved_albums


# use album uri to get tracks
### function to get tracks from a specified album (track name, artist, id)
def get_album_tracks(album_id,  limit=50, offset=0, market="AU"):
    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    album_tracks = [ ]
    
    # get initial list of tracks in album to determine length
    album_obj = sp.album_tracks(album_id = album_id, \
                                           limit = limit, offset = offset)
    num_album_tracks = album_obj['total']
    
    # loop through to get all album tracks
    while (offset < num_album_tracks):
        album_obj = sp.album_tracks(album_id = album_id, 
                                               limit = limit, offset = offset)

        # add track information to running list
        for track_obj in album_obj['items']:
            album_tracks.append({
                'track_name': track_obj['name'],
                'track_uri': track_obj['uri'],
                'track_artists': ', '.join([artist['name'] for artist in track_obj['artists']]),
                'track_artists_uri': ', '.join([artist['uri'] for artist in track_obj['artists']])
            })
            
        offset += limit
        
    return album_tracks

### function to get tracks from a specified album (track name, artist, id)
def get_top_tracks(artist_uri, country="AU"):
    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    
    top_tracks = [ ]
    
    # get list of top tracks from artist profile
    top_obj = sp.artist_top_tracks(artist_id = artist_uri, country=country )

    # add track information to running list
    for track_obj in top_obj['tracks']:
        top_tracks.append({
            'track_name': track_obj['name'],
            'track_uri': track_obj['uri'],
            'track_artists': ', '.join([artist['name'] for artist in track_obj['artists']]),
            'track_artists_uri': ', '.join([artist['uri'] for artist in track_obj['artists']])
        })
            
        
    return top_tracks

@app.route("/saved", methods=['GET'])
def create_playlist():

    session['token_info'], authorized = get_token(session)
    session.modified = True
    if not authorized:
        return redirect('/')
    sp = spotipy.Spotify(auth=session.get('token_info').get('access_token'))
    user = sp.me()['id']
    
    
    track_uri_list = playlist_df['track_uri'].tolist()
    playlist_name = f"{', '.join(artist)} only playlist " 
    
    # create playlist
    playlist_name = f"{', '.join(artist)} only playlist " 
    sp.user_playlist_create(user, name=playlist_name)
    
    # get playlist id of created playlist
    def get_playlist_id(user, playlist_name):
        playlist_id = ''
        playlists = sp.user_playlists(user)
        for playlist in playlists['items']:  # iterate through playlists I follow
            if playlist['name'] == playlist_name:  # filter for newly created playlist
                playlist_id = playlist['id']
        return playlist_id
    
    playlist_id = get_playlist_id(user, playlist_name)
    
    results = sp.playlist(playlist_id)
    pl_link = results['external_urls']['spotify']

    # add tracks from playlist_df to the playlist 
    sp.user_playlist_add_tracks(user, playlist_id, track_uri_list)
    

    return redirect(pl_link)    


if __name__ == "__main__": 
    threading.Timer(1.25, lambda: webbrowser.open(url)).start()   
    app.run(port=6137, debug=False)
