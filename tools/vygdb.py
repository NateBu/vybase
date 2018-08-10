'''
TODO: USe this for all STL https://gist.github.com/skyscribe/3978082
gdb --batch-silent -x thing_gdb_commands.py --args executablename arg1 arg2 arg3
//vygdb {"action":"variable_message","variable":"dividers","topic":"VineyardRowGenerator::generateRows::dividers"}
https://gcc.gnu.org/ml/libstdc++/2009-02/msg00056.html

print([gdb.TYPE_CODE_PTR,  gdb.TYPE_CODE_ARRAY,     gdb.TYPE_CODE_STRUCT,  gdb.TYPE_CODE_UNION,
  gdb.TYPE_CODE_ENUM,      gdb.TYPE_CODE_FLAGS,     gdb.TYPE_CODE_FUNC,    gdb.TYPE_CODE_INT,
  gdb.TYPE_CODE_FLT,       gdb.TYPE_CODE_VOID,      gdb.TYPE_CODE_SET,     gdb.TYPE_CODE_RANGE,
  gdb.TYPE_CODE_STRING,    gdb.TYPE_CODE_BITSTRING, gdb.TYPE_CODE_ERROR,   gdb.TYPE_CODE_METHOD,
  gdb.TYPE_CODE_METHODPTR, gdb.TYPE_CODE_MEMBERPTR, gdb.TYPE_CODE_REF,     gdb.TYPE_CODE_CHAR,
  gdb.TYPE_CODE_BOOL,      gdb.TYPE_CODE_COMPLEX,   gdb.TYPE_CODE_TYPEDEF, gdb.TYPE_CODE_NAMESPACE,
  gdb.TYPE_CODE_DECFLOAT,  gdb.TYPE_CODE_INTERNAL_FUNCTION])

'''

import gdb, time, re, json, math
from multiprocessing import Queue
global GDB_METHODS, ACTION_LIST
GDB_METHODS = {}
ACTION_LIST = []
user_command = Queue()
from DDPClient import DDPClient
logclient = DDPClient("ws://127.0.0.1:3000/websocket", auto_reconnect=True, auto_reconnect_timeout=1)
logclient.connect()

def ondebugstream(collection, id, fields, cleared):
  f = fields["args"][0]
  if "fromui" in f and f["fromui"] and "message" in f:
    user_command.put( f["message"] )

time.sleep(2)
logclient.on("changed", ondebugstream)

class ParseSourceException(Exception):
    pass

class _iterator:
  def __init__ (self, start, finish):
    self.item = start
    self.finish = finish
    self.count = 0

  def __iter__(self):
    return self

  def next(self):
    if self.item == self.finish:
      raise StopIteration
    count = self.count
    self.count = self.count + 1
    elt = self.item.dereference()
    self.item = self.item + 1
    return elt

def _vector(variable):
  first = variable['_M_impl']['_M_start']
  last = variable['_M_impl']['_M_finish']
  lngth = int(last-first)
  it = _iterator(first, last)
  x = []
  count = 0
  while count < lngth:
    try:
      x.append(something_to_json( it.next() ))
    except Exception as exc:
      print('vygdb._vector exception:',exc)
      break
    count += 1
  return x

def _tuple(head):
  # https://gcc.gnu.org/ml/libstdc++/2009-10/msg00102.html
  nodes = head.type.fields () # should be length 1
  head = head.cast (nodes[0].type)
  x = []
  count = 0
  while head is not None:
    nodes = head.type.fields()  # should be length 2
    impl = head.cast (nodes[-1].type)  # Right node is the actual class contained in the tuple.
    head = None if len(nodes)<2 else head.cast (nodes[0].type) # Left node is the next recursion parent, set it as head.
    fields = impl.type.fields ()
    if len (fields) < 1 or fields[0].name != "_M_head_impl":
        pass # I dont know what to do here
    else:
        x.append(something_to_json(impl['_M_head_impl']))
    count += 1
  return x

def _struct(variable):
  fields = []
  for field in variable.type.fields():
    if not (field.artificial or field.name is None):
      fields.append(field.name)
  isstring = all([field in ['_M_dataplus','_M_string_length','npos'] for field in fields])
  if len(fields) == 0 or isstring:
    try:
      if isstring:
        l = variable['_M_string_length']
        x = str(variable['_M_dataplus']['_M_p'].string (length = l))
      else:
        x = str(variable)
    except Exception as exc:
      x = str(variable)
  else:
    x = {}
    for name in fields:
      x[name] = something_to_json(variable[name])
  return x

def something_to_json(variable):
  typ = variable.type
  if typ.code == gdb.TYPE_CODE_TYPEDEF:
    typ = typ.strip_typedefs() 
  vtype = str(typ)
  x = None
  try:
    if typ.code in [gdb.TYPE_CODE_REF]:
      x = something_to_json(variable.referenced_value())
    elif typ.code in [gdb.TYPE_CODE_PTR]:
      x = something_to_json(variable.dereference())
    elif vtype.find("const std::vector") == 0 or vtype.find("std::vector") == 0:
      x = _vector(variable)
    elif vtype.find("const std::tuple") == 0 or vtype.find("std::tuple") == 0:
      x = _tuple(variable)
    elif vtype.find("const std::function") == 0 or vtype.find("std::function") == 0:
      x = None
    elif vtype.find("const std::map") == 0 or vtype.find("std::map") == 0:
      x = _map(variable)
    elif vtype.find("const std::allocator") == 0 or vtype.find("std::allocator") == 0:
      x = _map(variable)
    elif typ.code == gdb.TYPE_CODE_FLT:
      x = float(variable)
      if math.isnan(x):
        x = None
    elif typ.code == gdb.TYPE_CODE_INT:
      x = int(variable)
    elif typ.code == gdb.TYPE_CODE_BOOL:
      x = bool(variable)
    elif typ.code in [gdb.TYPE_CODE_ENUM]:
      x = '"'+str(variable)+'"' # enums return as string not value
    else:
      x = _struct(variable)
  except Exception as exc:
    print('vygdb.something_to_json Exception = ',exc)
    print('vtype = ',vtype)
    print('typ.code = ',typ.code)
    print('variable = ',variable)
  return x

def jsonify(variableinternal):
  top = gdb.newest_frame()
  vcount = 0
  try:
    for variableparts in re.split('\.|->',variableinternal):
      variable = top.read_var(variableparts) if vcount == 0 else variable[variableparts]
      vcount += 1
  except Exception as exc:
    print('vygdb.jsonify error: ',exc)
  else:    
    if variable.is_optimized_out:
      print('vygdb.jsonify error: ' + variableinternal + ' is optimized out at ' + self.source)
    else:
      try:
        return something_to_json(variable)
      except Exception as exc:
        print('vygdb.jsonify error: Could not access variable ' + variableinternal + ' at ' + self.source + '\n', exc)
  return None

class custom_breakpoint(gdb.Breakpoint):
  def __init__(self, source, action):
    gdb.Breakpoint.__init__(self, source)
    self.source = source
    self.variables = action['variables'] if 'variables' in action else []
    self.topic = action['topic'] if 'topic' in action else None
    self.method = action['method'] if 'method' in action else None
    self.action = action

  def stop(self):
    msg = {}
    for variablemap in self.variables:
      variableinternal = self.variables[variablemap]
      msg[variablemap] = jsonify(variableinternal)
  
    stop_ = False
    if msg and self.topic is None: # No topic just print
      for x in msg:
        print(x+':',msg[x])

    if self.method is not None and self.method in GDB_METHODS:
      try:
        stop_ = GDB_METHODS[self.method](msg, user_command)
      except Exception as exc:
        print('vygdb.custom_breakpoint error: Problem running method ' + str(self.method) + ' at ' + self.source + '\n', exc)

    if msg and self.topic is not None:
      data = {}
      for x in self.action:
        if x is not 'breakpoint':
          data[x] = msg if x == 'variables' else self.action[x]
      logclient.call("stream-topicstream", ["debugstream__",{'fromui':False,'message':data}])
    return stop_

def exit_handler (event):
  gdb.execute("quit")

def activate(actionlist, filterlist=[], exclusive=False):
  __action_assignment__(actionlist, filterlist, True, exclusive)

def deactivate(actionlist, filterlist=[], exclusive=False):
  __action_assignment__(actionlist, filterlist, False, exclusive)

def __action_assignment__(actionlist, filterlist=[], default_active=True, exclusive=True):
  global ACTION_LIST
  def _addaction_(action, make_active):
    if 'source' in action:
      if 'breakpoint' in action and not make_active:
        action['breakpoint'].delete()
        del action['breakpoint']
      elif 'breakpoint' not in action and make_active:
        action['breakpoint'] = custom_breakpoint(action['source'],action)
    else:
      print('vygdb Action:',action,'must have "source" ["variables", "topic", "labels", and "method" are optional fields]')

  ACTION_LIST = actionlist
  for action in ACTION_LIST:
    match = ('labels' in action and (not set(action['labels']).isdisjoint(filterlist)))
    match = match if not exclusive else not match
    if match:
      _addaction_(action, default_active)

def parse_sources(replace_paths=[]):
  sourcefiles = {'.py':{'comment':'\#'},
                  '.c':{'comment':'\/\/'}, '.cpp':{'comment':'\/\/'},
                  '.h':{'comment':'\/\/'}, '.hpp':{'comment':'\/\/'}}
  trigger = 'GDB'
  optionalspaces = '\s*?'
  actionlist = []
  sources = gdb.execute("info sources",to_string=True)
  pattern1 = 'Source files for which symbols have been read in:'
  pattern2 = 'Source files for which symbols will be read in on demand:'
  p1s = sources.find(pattern1)
  p2s = sources.find(pattern2)
  if p1s >= 0 and p2s >=0 :
    symbols = sources[p1s+len(pattern1):p2s].strip().split(', ') + sources[p2s+len(pattern2):].strip().split(', ')
    for filename in symbols:
      for rpath in replace_paths:
        filename = filename.replace(rpath['old'],rpath['new'])
      comment = None
      for ext in sourcefiles:
        if filename.endswith(ext):
          comment = sourcefiles[ext]['comment']
          break
      if comment is None:
        continue

      pattern = re.compile('^'+optionalspaces+comment+optionalspaces+trigger)
      try:
        with open(filename, 'r') as file:
          #match = re.findall("\/\*:::GDB:::(.*?):::GDB:::\*\/", file.read(), re.DOTALL); #MULTILINE!!
          for (i, line) in enumerate(file):
            mtch = re.match(pattern,line)
            if mtch:
              try:
                cmd = json.loads(re.sub(pattern,'',line.strip()))
                cmd['source'] = filename.split('/')[-1]+':'+str(i+1)
                for c in actionlist:
                  if cmd['source']==c['source']:
                    raise ParseSourceException("Duplicate source breakpoint")
                actionlist.append(cmd)
              except Exception as exc:
                print('  vygdb.parse_sources: Could not process potential debug point in '+filename+' at line '+str(i)+':\n'+line,exc)
      except Exception as exc:
        print('  vygdb.parse_sources: collection warning, failed reading of '+filename+':',exc)
  return actionlist

def get_command():
  cmd = user_command.get()
  if cmd.startswith('vyp '):
    print(jsonify(cmd[4:]))
    cmd = None
  elif cmd.startswith('activate '):
    lst = cmd.strip().split()[1:]
    activate(ACTION_LIST, lst, False)
    cmd = None
  elif cmd.startswith('deactivate '):
    lst = cmd.strip().split()[1:]
    deactivate(ACTION_LIST, lst, False)
    cmd = None
  return cmd

def stop(msg, user_command):
  return True

def init(replace_paths=[], methods={}):
  global GDB_METHODS
  GDB_METHODS = methods
  if 'stop' not in methods:
    GDB_METHODS['stop'] = stop

  # Second argument is a boolean but Im not sure what it means
  sub_id = logclient.subscribe("stream-topicstream", ["debugstream__",True])
  gdb.events.exited.connect(exit_handler)

  #gdb.execute("start") # Ensure shared libraries are loaded already (TODO, fix this? try-catch?)
  gdb.execute("set pagination off")
  gdb.execute("set python print-stack full")
  gdb.execute("set confirm off")
  return parse_sources(replace_paths)
  
def run():
  gdb.execute("run")
  lastcmd = None
  while True:
    cmd = get_command()
    if cmd is not None:
      try:
        cmd = lastcmd if len(cmd)==0 and lastcmd is not None else cmd
        lastcmd = cmd
        gdb.execute( cmd )
      except Exception as exc:
        print('vygdb.run problem executing ',cmd,exc)

if __name__ == 'main':
  actionlist = init()
  action_assignment(actionlist)
  run()