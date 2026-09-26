"""Model-name driven compatible Chat Completions client. Credentials are never saved."""
import base64
import json
import os
import re
import requests

class Client:
    def __init__(self,base_url=None,key_env='MODEL_API_KEY',timeout=300):
        self.base_url=(base_url or os.environ.get('MODEL_BASE_URL','https://api.openai.com/v1')).rstrip('/')
        self.key=os.environ.get(key_env,'');self.timeout=timeout
        if not self.key:raise ValueError(f'Set {key_env} in your shell; credentials are not stored in this package.')
    def complete(self,model,messages,temperature=None):
        payload={'model':model,'messages':messages}
        if temperature is not None:payload['temperature']=temperature
        response=requests.post(self.base_url+'/chat/completions',headers={'Authorization':'Bearer '+self.key},json=payload,timeout=self.timeout)
        if not response.ok:raise RuntimeError(f'Model request failed (HTTP {response.status_code}); response body omitted to avoid leaking credentials.')
        body=response.json();content=body['choices'][0]['message']['content']
        if not isinstance(content,str):raise RuntimeError('Model response did not contain text')
        return content

def code(text):
    m=re.search(r'```(?:python)?\s*(.*?)```',text,re.S)
    return (m[1] if m else text).strip()+'\n'

def json_object(text):
    text=re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip())
    return json.loads(text)

def image_block(path):
    return {'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode()}}
