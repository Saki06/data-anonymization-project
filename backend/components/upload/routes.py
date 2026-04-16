"""
Upload API Routes
Handles file uploads for CSV and Excel files
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import Dict, Any
import pandas as pd
import uuid
import io

router = APIRouter(prefix="", tags=["Upload"])

# Global storage for sessions (will be injected from main.py)
_sessions = {}


def set_sessions(sessions: Dict):
    """Set the sessions dictionary from main.py"""
    global _sessions
    _sessions = sessions


def create_session_from_bytes(filename: str, content: bytes) -> Dict[str, Any]:
    """
    Create a session from file bytes
    """
    global _sessions
    
    # Generate unique session ID
    session_id = str(uuid.uuid4())
    
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")
        
        # Clean column names (strip whitespace)
        df.columns = df.columns.str.strip()
        
        # Handle missing values for display
        df_clean = df.fillna('')
        
        # Prepare sample data (first 10 rows)
        sample_data = df_clean.head(10).to_dict('records')
        
        # Convert to JSON-serializable format
        for record in sample_data:
            for key, value in record.items():
                if pd.isna(value):
                    record[key] = None
                elif isinstance(value, (int, float)):
                    record[key] = float(value) if isinstance(value, float) else int(value)
                elif hasattr(value, 'item'):  # numpy types
                    record[key] = value.item()
                elif hasattr(value, 'tolist'):  # numpy arrays
                    record[key] = value.tolist()
        
        print(f"[UPLOAD] Created sample_data with {len(sample_data)} rows")
        
        # Create session data - include sample_data
        session_data = {
            'session_id': session_id,
            'filename': filename,
            'df': df,
            'columns': df.columns.tolist(),
            'shape': list(df.shape),
            'sample_data': sample_data,  # This was missing!
            'quasi_identifiers': [],
            'sensitive_attributes': [],
            'analysis_results': None,
            'anonymized_df': None
        }
        
        # Store in sessions
        _sessions[session_id] = session_data
        
        return session_data
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a CSV or Excel file and create a new session
    """
    global _sessions
    
    print(f"[UPLOAD] Starting upload for file: {file.filename}")
    
    # Validate file type
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    allowed_extensions = ['.csv', '.xlsx', '.xls']
    file_ext = '.' + file.filename.split('.')[-1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}"
        )
    
    try:
        # Read file content asynchronously
        content = await file.read()
        print(f"[UPLOAD] Read {len(content)} bytes")
        
        # Create session from bytes
        session_data = create_session_from_bytes(file.filename, content)
        print(f"[UPLOAD] Created session: {session_data['session_id']}")
        
        # Return session info
        result = {
            "session_id": session_data['session_id'],
            "filename": session_data['filename'],
            "shape": session_data['shape'],
            "columns": session_data['columns'],
            "sample_data": session_data.get('sample_data', [])
        }
        print(f"[UPLOAD] Returning: shape={result['shape']}, columns={len(result['columns'])}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[UPLOAD] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Upload error: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """
    Get session information including sample data
    """
    global _sessions
    
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = _sessions[session_id]
    df = session['df']
    
    # Prepare sample data (first 10 rows)
    df_clean = df.fillna('')
    sample_data = df_clean.head(10).to_dict('records')
    
    # Convert to JSON-serializable format
    for record in sample_data:
        for key, value in record.items():
            if pd.isna(value):
                record[key] = None
            elif isinstance(value, (int, float)):
                record[key] = float(value) if isinstance(value, float) else int(value)
            elif hasattr(value, 'item'):  # numpy types
                record[key] = value.item()
    
    return {
        "session_id": session_id,
        "filename": session.get('filename'),
        "columns": df.columns.tolist(),
        "shape": list(df.shape),
        "sample_data": sample_data,
        "quasi_identifiers": session.get('quasi_identifiers', []),
        "sensitive_attributes": session.get('sensitive_attributes', []),
        "has_analysis": session.get('analysis_results') is not None,
        "has_anonymized_data": session.get('anonymized_df') is not None
    }

