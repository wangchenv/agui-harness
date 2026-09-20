"""Two local domain adapters sharing agui_runtime, with explicit SQL preconditions."""
from agui_runtime import Action, Rejected


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('integer outside business range')


def inventory_input(payload):
    if set(payload) != {'sku', 'quantity', 'expected_version'}:
        raise ValueError('unexpected inventory fields')
    if not isinstance(payload['sku'], str) or not 0 < len(payload['sku']) <= 80:
        raise ValueError('SKU required')
    integer(payload['quantity'], 1, 100)
    integer(payload['expected_version'], 0, 1_000_000)
    return payload


def reserve_input(payload):
    if set(payload) != {'room', 'start', 'end'}:
        raise ValueError('unexpected reservation fields')
    if not isinstance(payload['room'], str) or not 0 < len(payload['room']) <= 80:
        raise ValueError('room required')
    integer(payload['start'], 0, 10_000_000_000)
    integer(payload['end'], 0, 10_000_000_000)
    if not 0 < payload['end'] - payload['start'] <= 14400:
        raise ValueError('invalid duration')
    return payload


def take_stock(db, actor, payload):
    changed = db.execute('''UPDATE inventory SET quantity=quantity-?,version=version+1
        WHERE tenant=? AND sku=? AND version=? AND quantity>=?''',
        (payload['quantity'], actor.tenant_id, payload['sku'], payload['expected_version'], payload['quantity']))
    if changed.rowcount != 1: raise Rejected('stock_or_version_conflict')
    row = db.execute('SELECT quantity,version FROM inventory WHERE tenant=? AND sku=?',
                     (actor.tenant_id, payload['sku'])).fetchone()
    return {'sku': payload['sku'], 'remaining': row['quantity'], 'version': row['version']}


def reserve_room(db, actor, payload, *, allow_overlap=False):
    room = db.execute('SELECT 1 FROM rooms WHERE tenant=? AND id=?', (actor.tenant_id, payload['room'])).fetchone()
    if not room: raise Rejected('room_unavailable')
    overlap = db.execute('''SELECT 1 FROM reservations WHERE tenant=? AND room=?
        AND start<? AND end>?''', (actor.tenant_id, payload['room'], payload['end'], payload['start'])).fetchone()
    if overlap and not allow_overlap: raise Rejected('reservation_conflict')
    cursor = db.execute('INSERT INTO reservations(tenant,subject,room,start,end) VALUES (?,?,?,?,?)',
                        (actor.tenant_id, actor.subject_id, payload['room'], payload['start'], payload['end']))
    return {'reservation_id': cursor.lastrowid, 'room': payload['room'], 'start': payload['start'], 'end': payload['end']}


def actions(*, allow_overlap=False):
    return {'inventory.take': Action('1', inventory_input, take_stock),
            'room.reserve': Action('1', reserve_input, lambda db, actor, payload:
                                   reserve_room(db, actor, payload, allow_overlap=allow_overlap))}


def create_domain_tables(db):
    db.executescript('''
        CREATE TABLE inventory(tenant TEXT,sku TEXT,quantity INTEGER,version INTEGER,PRIMARY KEY(tenant,sku));
        CREATE TABLE rooms(tenant TEXT,id TEXT,PRIMARY KEY(tenant,id));
        CREATE TABLE reservations(id INTEGER PRIMARY KEY,tenant TEXT,subject TEXT,room TEXT,start INTEGER,end INTEGER);
        INSERT INTO inventory VALUES ('team','laptop',5,0);
        INSERT INTO rooms VALUES ('team','room-1');
    ''')
