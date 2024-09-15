import logging
import sys
import ytmusicapi
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import os
from dotenv import load_dotenv
import time  # For rate limiting
from requests.exceptions import HTTPError

# Load environment variables from .env file
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Authentication (Retrieve credentials from environment variables)
spotify_client_id = os.environ.get('SPOTIFY_CLIENT_ID')
spotify_client_secret = os.environ.get('SPOTIFY_CLIENT_SECRET')
spotify_redirect_uri = 'http://localhost:8888/callback'  # Corrected redirect URI

# YouTube Music authentication using OAuth credentials
ytmusic = ytmusicapi.YTMusic('oauth.json')  
logger.info("YTMusic object created successfully!")

def authenticate_spotify():
    """Authenticates with Spotify and returns a Spotipy client object."""

    try:
        scope = "playlist-read-private"
        sp_oauth = SpotifyOAuth(
            client_id=spotify_client_id,
            client_secret=spotify_client_secret,
            redirect_uri=spotify_redirect_uri,  # Using the corrected redirect URI
            scope=scope
        )
        auth_url = sp_oauth.get_authorize_url()
        print(f"Please visit this URL to authorize the application: {auth_url}")

        while True:  # Loop until a valid code is provided
            try:
                auth_code = input("Enter the FULL authorization code from the URL you were redirected to: ")
                token_info = sp_oauth.get_access_token(auth_code, as_dict=False)
                return spotipy.Spotify(auth=token_info)
            except spotipy.SpotifyOauthError as e:
                logging.error(f"Error retrieving Spotify access token: {e}")
                print("Invalid authorization code. Please try again.")

    except Exception as e:
        logging.error(f"Error during Spotify authentication: {e}")
        return None


def transfer_playlist(sp, spotify_playlist_id):
    """Transfers a Spotify playlist to YouTube Music, handling pagination."""
    try:
        # Fetch Spotify Playlist (initial request)
        spotify_playlist = sp.playlist(spotify_playlist_id)
        tracks_data = spotify_playlist['tracks']

        # Initialize variables for pagination
        offset = 0
        limit = 100
        all_spotify_tracks = tracks_data['items']

        # Create YouTube Music Playlist
        yt_playlist_id = ytmusic.create_playlist(spotify_playlist['name'], description="Imported from Spotify")
        logging.info(f"Created YouTube Music playlist: {spotify_playlist['name']}")

        # Fetch all tracks from the Spotify playlist using pagination
        while tracks_data['next']:  
            offset += limit
            tracks_data = sp.next(tracks_data)  
            all_spotify_tracks.extend(tracks_data['items'])  # Add tracks to the list

        # Track Existing YouTube Music Songs for Duplicate Handling
        yt_library = ytmusic.get_library_upload_songs(limit=None)
        yt_library_song_ids = {song['videoId'] for song in yt_library}

        # Add Tracks to YouTube Music Playlist, Handling Duplicates and Not Found
        not_found_tracks = []

        for track_item in all_spotify_tracks:
            try:
                track = track_item['track']
                if not track:  
                    logging.warning("Skipping track with no metadata")
                    continue
                track_name = track['name']
                artist_name = track.get('artists', [{}])[0].get('name', "Unknown Artist")  

                search_query = f"{track_name} {artist_name}"
                search_results = ytmusic.search(search_query)

                if search_results:
                    # Handle Duplicates
                    added = False
                    for result in search_results:
                        try:
                            yt_track_id = result['videoId']
                            if yt_track_id not in yt_library_song_ids:
                                ytmusic.add_playlist_items(yt_playlist_id, [yt_track_id])
                                logging.info(f"Added track: {track_name} by {artist_name}")
                                yt_library_song_ids.add(yt_track_id)
                                added = True
                                time.sleep(1)
                                break
                        except KeyError:
                            # Skip track with a warning
                            logging.warning(f"Unexpected search result format for '{track_name}' by '{artist_name}'. Skipping track.")
                            continue 
                    if not added:
                        logging.warning(f"Skipped duplicate: '{track_name}' by '{artist_name}'")
                else:
                    not_found_tracks.append((track_name, artist_name))

            except HTTPError as e:
                logging.error(f"Error searching/adding track: {track_name} by {artist_name}. Status Code: {e.response.status_code}")
            except Exception as e:  # Catch any unexpected error
                logging.error(f"Unexpected error adding track: {track_name} by {artist_name}. Error: {e}")

        # Log not found songs at the end
        if not_found_tracks:
            logging.info("Tracks not found on YouTube Music:")
            for track_name, artist_name in not_found_tracks:
                logging.info(f"- '{track_name}' by '{artist_name}'")

    except Exception as e:
        logging.error(f"Error transferring playlist: {e}")
        logging.exception(sys.exc_info()[2])  
 


if __name__ == "__main__":
    # Spotify Authentication
    sp = authenticate_spotify()
    if sp is None:
        print("Authentication failed. Please check your credentials and try again.")
    else:
        # Get user input for Spotify playlist ID
        spotify_playlist_id = input("Enter Spotify playlist ID: ")

        # Transfer the playlist
        transfer_playlist(sp, spotify_playlist_id)
