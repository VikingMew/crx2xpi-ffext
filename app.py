## coding: utf-8

from flask import Flask
from flask import render_template, request, Response, make_response, redirect, jsonify

import datetime, re, time, os, shutil
import json, sqlite3
from cStringIO import StringIO
    
app = Flask(__name__)

## models
class File:
    def __init__(self, token, stream):
        if not os.path.exists('/tmp/uploads'): os.mkdir('/tmp/uploads')
        import md5
        self.id = md5.md5('%.6f' % time.time()).hexdigest()
        self.filename = '/tmp/uploads/' + self.id + '.' + token[token.rfind('.')+1:]
        self.stream = stream

    def save(self):
        with open(self.filename, 'w') as f:
            f.write(self.stream.read())

class DBObject:
    FIELD_CONV = {
        'objectId': 'id',
        'c_id': 'id',
        'id': 'id',
        'created_at': 'c_createdAt',
    }
    OPER_CONV = {
        'gt': '>',
        'lt': '<',
        'gte': '>=',
        'lte': '<=',
        'ne': '!=',
        'contains': 'like'
    }

    def __init__(self, **kwargs):
        import md5
        self.dict = dict(kwargs)
        self.conn = sqlite3.connect('my.db')
        self.table_name = self.__class__.__name__
        self.dict['id'] = md5.md5('%.6f' % time.time()).hexdigest()
        self.dict['createdAt'] = time.time()
        self.dict['updatedAt'] = time.time()

    def set(self, key, value):
        self.dict[key.lower()] = value

    def get(self, key, default=''):
        return self.dict.get(key.lower(), default)

    @property
    def id(self):
        return self.dict.get('id')

    @property
    def created_at(self):
        return datetime.datetime.fromtimestamp(self.dict['createdAt']).strftime("%Y-%m-%d %H:%M:%S")
        
    @property
    def updated_at(self):
        return datetime.datetime.fromtimestamp(self.dict['updatedAt']).strftime("%Y-%m-%d %H:%M:%S")

    def get_cols(self):
        c = self.conn.cursor()
        cols = c.execute("select * from sqlite_master where type = 'table' and name= '" + self.table_name + "'").fetchone()[-1].lower()

        cols = cols[cols.find('(')+1:cols.rfind(')')].replace('`', '')
        cols = re.split(r',\s*', cols)
        cols = [re.split(r'\s', _)[0] for _ in cols]
        cols = [_ if _ == 'id' else _[2:] for _ in cols]

        return cols
        
    def select(self, order='', limit=10, **kwargs):
        c = self.conn.cursor()
        where = ''
        for k in kwargs:
            field = k.split('__')[0]
            oper = '=' if '__' not in k else DBObject.OPER_CONV.get(k.split('__')[1], '=')
            if oper == 'like': kwargs[k] = '%' + kwargs[k] + '%'
            where += ' AND `' + DBObject.FIELD_CONV.get(field, 'c_' + field) + '` ' + oper + ' ?'


        if where != '':
            where = ' WHERE ' + where[5:]
        where_args = [_.decode('utf-8') if isinstance(_, str) else _ for _ in kwargs.values()]

        if order != '':
            order = ' ORDER BY ' + ','.join([DBObject.FIELD_CONV.get(_, 'c_' + _) + (' desc' if _.startswith('-') else '') for _ in order.split(',')]).replace('-', '')

        where += order
        where += ' LIMIT {}'.format(limit)
        
        cols = self.get_cols()

        r = []
        for res in c.execute("SELECT * FROM " + self.table_name + where, where_args):
            k = eval(self.__class__.__name__ + '()')
            for i in range(0, len(res)):
                try:
                    x = json.loads(res[i])
                except:
                    x = res[i]
                k.set(cols[i], x)
            r.append(k)
        return r
        
    def destroy(self):
        c = self.conn.cursor()
        c.execute("DELETE FROM " + self.table_name + " WHERE id = ?", (self.id,))
        self.conn.commit()
        return True

    def save(self):
        self.dict['updatedAt'] = time.time()
        
        if 'objectId' in self.dict:
            self.dict['id'] = self.dict['objectId']
            del self.dict['objectId']

        create = "CREATE TABLE IF NOT EXISTS " + self.table_name + " (id TEXT PRIMARY KEY"
        for c in self.dict.keys():
            if c.lower() == 'id': continue
            create += ", `c_" + c + "` " + ("INTEGER" if isinstance(self.dict[c], int) else "REAL" if isinstance(self.dict[c], float)  else "TEXT")
        create += ")"
        c = self.conn.cursor()
        c.execute(create)

        cols = self.get_cols()
        for _ in list(self.dict.keys()):
            if _.lower() not in cols: del self.dict[_]
        colcount = len(self.dict)

        sql = "REPLACE INTO " + self.table_name + "(" + ','.join([('' if _ == 'id' else 'c_') + _ for _ in self.dict.keys()]) + ") VALUES (" + ("?," * colcount)[:-1] +  ")"
        vals = tuple(json.dumps(_) if isinstance(_, type([])) or isinstance(_, type({})) else _ for _ in self.dict.values())
        c.execute(sql, vals)
        self.conn.commit()
        
        return self

class Queue(DBObject):
    pass
        
def shell(shellargs):
    from subprocess import Popen, PIPE, STDOUT
    
    p = Popen(shellargs, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT, close_fds=True)
    output = p.stdout.read()
    return output

def web_ext(cmd, source_dir, artifact_dir, **kwparams):
    shellargs = 'web-ext {} --source-dir="{}" --artifacts-dir="{}"'.format(cmd, source_dir, artifact_dir)
    for k, v in kwparams.items():
        shellargs += ' ' + k.replace('_', '-')
        if v: shellargs += '="{}"'.format(v)
    
    return shell(shellargs)
    
@app.route('/queue', methods=['GET','POST'])
def queue():
    def yield_file(p):
        with open(p, 'rb') as f:
            while True:
                r = f.read(1024000)
                if not r: break
                yield r

    id = request.args.get('id') or request.form.get('id')
    if id:
        q = Queue().select(id=id)
        if not q: return jsonify(error='Invalid id.')
        if 'artifact' in request.args:
            art_dir = q.get('artifact_dir')
            xpis = [_ for _ in os.listdir(art_dir) if _.endswith('.xpi')]
            if len(xpis) == 0: return jsonify(error='XPI not found.')
            path = art_dir + '/' + xpis[0]
            return Response(yield_file(path), mimetype='application/octstream')
        else:
            return jsonify(status=q[0].get('flag'), result=q[0].get('result'))

                        
    def sign_view(f):
        apikey = request.form.get('apikey')
        apisecret = request.form.get('apisecret')
        if not apikey or not apisecret:
            return jsonify(error='No API Key or API Secret given.')
        if f.endswith('.zip') or f.endswith('.crx'):
            shell('cd /tmp/uploads; mkdir {f4}; cd {f4}; unzip "{f}"'.format(f=f, f4=f[:-4]))
            os.unlink(f)
            f = f[:-4]
            for _ in os.listdir(f):
                if (_.startswith('_') or _.startswith('.')) and _ != '_locale':
                    if os.path.isdir(f + '/' + _):
                        shutil.rmtree(f + '/' + _)
                    else:
                        os.unlink(f + '/' + _)
        # find manifest
        mf = shell('find "{}" -iname manifest.json'.format(f)).split('\n')[0]
        j = manifest(open(mf).read())
        with open(mf, 'w') as fo:
            fo.write(j)
        f = mf[:mf.rfind('/')]
        # enqueue
        q = Queue(flag=0, source_dir=f, artifact_dir=f + '/artifact', apikey=apikey, apisecret=apisecret, act='sign', result='')
        q.save()
        return jsonify(id=q.id, status=0)
        
    def manifest_view(j):
        return Response(manifest(j), mimetype='application/json')
        
        
    if 'file' in request.files:
        sr = request.files['file'].stream
        filename = request.files['file'].filename
        if filename.endswith('.zip'): # sign
            f = File(filename, sr)
            f.save()
            return sign_view(f.filename)
        elif filename.endswith('.json'): # manifest
            return manifest_view(sr.read())
        else: # invalid
            return jsonify(error='Invalid file.')
    elif 'manifest' in request.form:
        return manifest_view(request.form['manifest'])
    elif 'git' in request.form:
        u = request.form['git']
        u = u.replace('"', '').replace("'", '').replace('$', '')
        shell('cd /tmp/uploads; git clone "{}"'.format(u))
        src_dir = '/tmp/uploads/' + u.split('/')[-1]
        return sign_view(src_dir)
        
    return jsonify(error='Invalid post data.')
        
        
def manifest(j):
    print j

    j = json.loads(j)
    
    if 'update_url' in j: del j['update_url']
    if j.get('background', {}).get('persistent'): del j['background']['persistent']
    if 'permissions' in j: j['permissions'] = list(set(j['permissions']))
    if j.get('options_ui', {}).get('chrome_style'): del j['options_ui']['chrome_style']
    if 'options_page' in j:
        j['options_ul'] = { 'page': j['options_page'], 'open_in_tab': True }
        del j['options_page']
        
    j = json.dumps(j, indent=4)
    return j
    
    
@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    return resp
    

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == 'clear':
            for _ in Queue().select(flag=1, limit=1, updatedAt__lt=time.time()-3600*4):
                _.set(flag=2)
                _.save()
                shutil.rmtree(_.get('source_dir'))
            
        while sys.argv[1] == 'dequeue':
            time.sleep(1)
            for _ in Queue().select(flag=0, limit=1):
                print _.id
                act = _.get('act')
                if act == 'sign':
                    result = web_ext('build', _.get('source_dir'), _.get('artifact_dir'))
                    result += '\n**SIGN:\n' + web_ext('sign', _.get('source_dir'), _.get('artifact_dir'), api_key=_.get('apikey'), api_secret=_.get('apisecret'))
                    _.set('result', result)
                    _.set('flag', 1)
                    _.save()
                
    else:
        app.debug = True
        app.run(port=5010)