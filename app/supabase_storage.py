import os
from werkzeug.utils import secure_filename
from datetime import datetime
from supabase import Client
from app.extensions import supabase,buckets
from flask import current_app

def upload_to_supabase(file, bucket_name, user_id, file_type='document'):
    """Uploading a file to Supabase Storage"""
    try:
        # Generate a unique filename
        timestamp = datetime.now().timestamp()
        extension = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        filename = secure_filename(f"{file_type}_{user_id}_{timestamp}.{extension}")
        
        # Upload the file
        file_bytes = file.read()
        result = supabase.storage.from_(bucket_name).upload(
            file=file_bytes,
            path=filename,
            file_options={"content-type": file.content_type}
        )
        
        if result:
            # Get the public URL
            public_url = supabase.storage.from_(bucket_name).get_public_url(filename)
            return filename, public_url
        
        return None, None
        
    except Exception as e:
        current_app.logger.error(f"Error uploading to Supabase: {str(e)}")
        return None, None

def delete_from_supabase(filename, bucket_name):
    """Delete file from Supabase Storage"""
    try:
        result = supabase.storage.from_(bucket_name).remove([filename])
        return result
    except Exception as e:
        current_app.logger.error(f"Error deleting from Supabase: {str(e)}")
        return False

def get_file_url(filename, bucket_name):
    """Get public URL file"""
    try:
        return supabase.storage.from_(bucket_name).get_public_url(filename)
    except Exception as e:
        current_app.logger.error(f"Error getting file URL: {str(e)}")
        return None


