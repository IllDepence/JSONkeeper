""" Classes for handling Activity Stream resources.
"""

import datetime
import dateutil.parser
import json
import uuid
from collections import OrderedDict
from jsonkeeper.models import db, JSON_document


class ASWrapper():

    def __init__(self, store_id):
        self.dic = OrderedDict()
        self.store_id = store_id

    def get(self, key):
        return self.dic[key]

    def get_dict(self):
        """ Return the Collection as a Python dict.
        """

        return self.dic

    def get_json(self):
        """ Return the Collection as JSON.
        """

        return json.dumps(self.dic)

    def store(self):
        json_doc = JSON_document.query.filter_by(id=self.store_id).first()
        if json_doc:
            json_doc.json_string = self.get_json()
            db.session.commit()
        else:
            json_doc = JSON_document(id=self.store_id,
                                     access_token=str(uuid.uuid4()),
                                     json_string=self.get_json())
            db.session.add(json_doc)
            db.session.commit()


class ASCollection(ASWrapper):

    def __init__(self, ld_id, store_id):
        """ Create an empty Collection given an ID and a file system path to
            save to.
        """

        super().__init__(store_id)

        col = OrderedDict()
        col['@context'] = 'https://www.w3.org/ns/activitystreams'
        col['type'] = 'Collection'
        col['id'] = ld_id
        col['summary'] = ('Activities generated based on the creation of many '
                          'Curations')
        col['totalItems'] = 0
        col['first'] = None
        col['last'] = None
        self.dic = col
        self.total_items = 0
        self.first = None
        self.last = None

    def restore_from_json(self, col_json, page_docs):
        """ Restore from JSON
        """

        self.dic = json.loads(col_json, object_pairs_hook=OrderedDict)
        for pd in page_docs:
            page = ASCollectionPage(None, pd.id)
            page.from_json(pd.json_string)
            self.add(page)

    def remove(self, to_rem):
        """ Remove a CollectionPage.

            Note: implemented BUT NOT TESTED for AS moderation (in case a
                  CollectionPage gets taken out of the AS).
            Note #2: may be unnecessary b/c restore_from_json can be used to
                     only selectively add
        """

        self.total_items -= 1
        if self.total_items == 0:
            self.first = None
            self.last = None
        elif self.total_items > 0:
            if to_rem.get('id') == self.last.get('id'):
                self.last = to_rem.prev
                self.last.unset_next()
            elif to_rem.get('id') == self.first.get('id'):
                self.first = to_rem.next
                self.first.unset_prev()
            else:
                to_rem.prev.set_next(to_rem.next)
                to_rem.next.set_prev(to_rem.prev)
        else:
            print('WARNING: Collection structure is broken.')
        to_rem.unset_part_of()
        to_rem.unset_prev()
        to_rem.unset_next()

    def add(self, to_add):
        """ Add a CollectionPage.
        """

        to_add.set_part_of(self)
        self.total_items += 1
        if self.total_items == 1:
            self.first = to_add
            self.last = to_add
        elif self.total_items > 1:
            cur = self.last
            while True:
                if to_add.after(cur):
                    # somewhere inbetween
                    cur.set_next(to_add)
                    to_add.set_prev(cur)
                    if cur.get('id') != self.last.get('id'):
                        cur.next.set_prev(to_add)
                        to_add.set_next(cur.next)
                    else:
                        # at the very end
                        self.last = to_add
                    break
                if cur.get('id') == self.first.get('id') and \
                        to_add.prev is None:
                    # at the very beginning
                    self.first = to_add
                    cur.set_prev(to_add)
                    to_add.set_next(cur)
                    break
                cur = cur.prev
                if not cur:
                    print('WARNING: Collection structure is broken.')
        else:
            print('WARNING: Collection structure is broken.')

        self._update_dict()
        self.store()

    def _update_dict(self):
        """ Update self.dic dict from member values.
        """

        self.dic['first'] = self.first.get('id')
        self.dic['last'] = self.last.get('id')
        self.dic['totalItems'] = self.total_items


class ASCollectionPage(ASWrapper):

    def __init__(self, ld_id, store_id):
        """ Create an empty CollectionPage.
        """

        super().__init__(store_id)

        cop = OrderedDict()
        # FIXME: hardcoded for Curation
        cop['@context'] = ['https://www.w3.org/ns/activitystreams',
                           'http://iiif.io/api/presentation/2/context.json',
                           ('http://codh.rois.ac.jp/iiif/curation/1/context.js'
                            'on')]
        cop['type'] = 'CollectionPage'
        cop['id'] = ld_id
        cop['summary'] = ('Activities generated based on the creation of one '
                          'Curation')
        cop['partOf'] = None
        # cop['prev']
        # cop['next']
        cop['items'] = []
        self.dic = cop
        self.part_of = None
        self.prev = None
        self.next = None

    def from_json(self, json_str):
        self.dic = json.loads(json_str, object_pairs_hook=OrderedDict)
        self.part_of = self.dic['partOf']
        if self.dic.get('prev'):
            self.prev = self.dic['prev']
        if self.dic.get('next'):
            self.next = self.dic['next']

    def set_part_of(self, col):
        self.part_of = col
        self.dic['partOf'] = self.part_of.get('id')
        self.store()

    def unset_part_of(self):
        self.part_of = None
        self.dic['partOf'] = None
        self.store()

    def unset_prev(self):
        self.dic['prev'] = None
        self.prev = None
        self.store()

    def unset_next(self):
        self.next = None
        self.dic['next'] = None
        self.store()

    def set_prev(self, other):
        self.prev = other
        if self.prev:
            self.dic['prev'] = self.prev.get('id')
        else:
            self.dic.pop('prev', None)
        self.store()

    def set_next(self, other):
        self.next = other
        if self.next:
            self.dic['next'] = self.next.get('id')
        else:
            self.dic.pop('next', None)
        self.store()

    def end_time(self):
        """ Return the latest time any of the contained Activity ended.
        """

        latest = datetime.datetime.fromtimestamp(0)
        for itm in self.dic['items']:
            itm_end = dateutil.parser.parse(itm['endTime'])
            if itm_end > latest:
                latest = itm_end
        return latest

    def after(self, other):
        """ Return True if this CollectionPage's Activities ended after other's
            Activities. Otherwise return False.

            NOTE: This function assumes that end times of Activities bundled in
                  CollectionPages never overlap. Formally, given two distinct
                  CollectionPages P and S, for any two Activities p∈ P and s∈ S
                  the comparison whether one of the Activities ended later
                  endₚ>endₛ is consitently True or consitently False.
        """

        return self.end_time() > other.end_time()

    def add(self, activity):
        """ Add an Activity to the CollectionPage's items.
        """

        self.dic['items'].append(activity)
        self.store()


class ActivityBuilder():
    """ Static methods for building activities.
    """

    @staticmethod
    def _build_basic(**kwargs):
        act = OrderedDict()
        act['@context'] = 'https://www.w3.org/ns/activitystreams'
        act['id'] = str(uuid.uuid4())
        for key, val in kwargs.items():
            act[key] = val
        if 'endTime' not in kwargs.keys():
            act['endTime'] = datetime.datetime.now().isoformat()
        return act

    @staticmethod
    def build_reference(origin, obj, **kwargs):
        act = ActivityBuilder._build_basic(**kwargs)
        act['@context'] = ['https://www.w3.org/ns/activitystreams',
                           ('https://illdepence.github.io/curationactivity/jso'
                            'n-ld/context.json')]
        act['type'] = 'Reference'
        act['origin'] = origin
        act['object'] = obj
        return act

    @staticmethod
    def build_offer(origin, obj, target, **kwargs):
        act = ActivityBuilder._build_basic(**kwargs)
        act['type'] = 'Offer'
        act['origin'] = origin
        act['object'] = obj
        act['target'] = target
        return act

    @staticmethod
    def build_create(obj, **kwargs):
        act = ActivityBuilder._build_basic(**kwargs)
        act['type'] = 'Create'
        act['object'] = obj
        return act
