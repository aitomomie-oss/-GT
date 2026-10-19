"""Read secrets without displaying their contents or persisting credentials."""
def jquants_key():
    import os
    import streamlit as st
    try:
        value=st.secrets.get('JQUANTS_API_KEY')
        if not value:
            section=st.secrets.get('jquants',{})
            value=section.get('api_key') if hasattr(section,'get') else None
        if isinstance(value,str) and value.strip(): return value.strip()
    except (FileNotFoundError,KeyError):
        pass
    except Exception:
        # Malformed secret files must not leak their contents through an exception.
        return ''
    return os.environ.get('JQUANTS_API_KEY','')
