import sys,os,uuid
from pathlib import Path
h=Path.cwd();v=h.parents[1]/'vendor/DeepTutor'
sys.path[:0]=[str(h),str(v),str(h/'.runtime/browser-check-12d290667b/python-deps')]
sys.path.append('E:/项目/heart/project/integration/discrete-math-tutor/.venv-deeptutor/Lib/site-packages')
from dotenv import load_dotenv
load_dotenv('E:/项目/heart/project/integration/discrete-math-tutor/.env')
os.environ['TUTOR_PSYCHOLOGY_DIR']='E:/项目/heart/project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3'
os.environ['DEEPTUTOR_HOME']=str(h/'.runtime'/('task8-native-'+uuid.uuid4().hex[:8]))
os.environ['MEM0_ENABLED']='0'
import pytest
raise SystemExit(pytest.main([*sys.argv[1:],'-q','--basetemp',str(h/'.runtime'/('task8-pytest-'+uuid.uuid4().hex[:8]))]))
