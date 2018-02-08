""" Classes for handling IIIF resources.
"""

import datetime
import dateutil.parser
import json
import uuid
from collections import OrderedDict


class Curation():

    def __init__(self, cur_id, label=None):
        """ Create an empty Curation.
        """

        if label is None:
            label = cur_id

        cur = OrderedDict()
        cur['@context'] = ['http://iiif.io/api/presentation/2/context.json',
                           'http://codh.rois.ac.jp/iiif/curation/1/context.json']
        cur['@type'] = 'cr:Curation'
        cur['@id'] = cur_id
        cur['label'] = label
        cur['selections'] = []
        self.cur = cur

    def from_json(self, json_str):
        """ Load curation from JSON. Overwrites previous contents.
        """

        self.cur = json.loads(json_str, object_pairs_hook=OrderedDict)

    def _create_empty_range(self, within, within_label, label, ran_id):
        """ Create an empty Range. Not supposed to be called from outside.
        """

        if ran_id is None:
            ran_id = str(uuid.uuid4())
        if label is None:
            label = ran_id
        if within_label is None:
            within_label = within

        ran = OrderedDict()
        ran['@id'] = ran_id
        ran['@type'] = 'sc:Range'
        ran['label'] = label
        ran['within'] = OrderedDict()
        ran['within']['@id'] = within
        ran['within']['@type'] = 'sc:Manifest'
        ran['within']['label'] = within_label
        ran['members'] = []
        return ran

    def add_and_fill_range(self, within, canvases, within_label=None,
                           label=None, ran_id=None):
        """ Add Range and fill with Canvases. Return the Range's id
            (generated randomly when not given).
        """

        ran = self._create_empty_range(within, within_label, label, ran_id)
        for can in canvases:
            ran['members'].append(can)
        self.cur['selections'].append(ran)
        return ran['@id']

    def add_empty_range(self, within, within_label=None, label=None,
                        ran_id=None):
        """ Add empty Range. Return the Range's id (generated randomly when
            not given).
        """

        ran = self._create_empty_range(within, within_label, label, ran_id)
        self.cur['selections'].append(ran)
        return ran['@id']

    def create_xywh_canvas(self, can_id, x, y, w, h, label=None):
        """ Create a Canvas with xywh fragment. The Canvas has to be added to
            a Range manually afterwards.
        """

        can = OrderedDict()
        can['@id'] = '{}#xywh={},{},{},{}'.format(can_id, x, y, w, h)
        can['@type'] = 'sc:Canvas'
        if label is None:
            label = can['@id']
        can['label'] = label
        return can

    def add_xywh_canvas(self, ran_id, can_id, x, y, w, h, label=None):
        """ Add a Canvas with xywh fragment to the specified Range.
        """

        can = self.create_xywh_canvas(can_id, x, y, w, h, label)
        found = False
        for ran in self.cur['selections']:
            if ran['@id'] == ran_id:
                ran['members'].append(can)
                found = True
        if not found:
            print('WARNING: range with id {} not found'.format(ran_id))

    def get_dict(self):
        """ Return the Curation as a Python dict.
        """

        return self.cur

    def get_json(self):
        """ Return the Curation as JSON.
        """

        return json.dumps(self.cur)

    def get_id(self):
        return self.cur['@id']

    def get_all_canvas_ids(self):
        """ Return the IDs of all Canvases across the Curation's Ranges.
        """

        cnvss = []
        for ran in self.cur['selections']:
            for can in ran['canvases']:
                if type(can) == str:
                    cnvss.append(can)
                else:
                    cnvss.append(can['@id'])
        return cnvss

    def get_range_summary(self):
        """ Return a list of all Range IDs with the IDs of the Manifests they
            refer to.
        """

        # Bad ad hoc spaghetti code ahead.
        #
        # Instead of kind of seaching for/guessing one reference to a Manifest
        # this should return all entities referenced except for the Curation
        # itself.

        ret = []
        for ran in self.cur['selections']:
            dic = {}
            dic['ran'] = ran['@id']
            w = ran['within']
            if type(w) == str or \
               (type(w) == list and len(w) == 1 and type(w[0]) == str):
                dic['man'] = w
            elif type(w) == list:
                for itm in w:
                    if (type(itm) == dict or type(itm) == OrderedDict) and \
                       '@type' in itm.keys() and \
                       itm['@type'] == 'sc:Manifest':
                        # definitely links to a Manifest, done
                        dic['man'] = itm['@id']
                        break
                    elif type(itm) == str:
                        # may link to a Manifest; save it and keep looking
                        dic['man'] = itm
                    elif type(itm) == dict or type(itm) == OrderedDict:
                        # may link to a Manifest; save it and keep looking
                        dic['man'] = itm['@id']
                    else:
                        print(('WARNING: Can\'t parse a Range\'s within value '
                               '(list item).\n>>> {}'.format(json.dumps(itm))))
            elif type(w) == dict or \
                 type(w) == OrderedDict:
                mby_man = self._extract_manifest_id(w)
                if mby_man:
                    dic['man'] = mby_man
                else:
                    continue
            else:
                print(('WARNING: Can\'t parse a Range\'s within value.\n'
                       '>>> {}'.format(json.dumps(w))))
            ret.append(dic)
        return ret

    def _extract_manifest_id(self, dic):
        if '@type' in dic.keys():
            if dic['@type'] == 'sc:Manifest':
                return dic['@id']
            else:
                print(('WARNING: Expected a sc:Manifest but got something diff'
                       'erent.'))
                return None
        else:
            print('WARNING: Making assumptions about classes.')
            return dic['@id']


class ASCollection():

    def __init__(self, ld_id, store_id, db, JSON_document_class):
        """ Create an empty Collection given an ID and a file system path to
            save to.
        """

        col = OrderedDict()
        col['@context'] = 'https://www.w3.org/ns/activitystreams'
        col['type'] = 'Collection'
        col['id'] = ld_id
        col['summary'] = ('Activities generated based on the creation of many '
                          'Curations')
        col['totalItems'] = 0
        col['first'] = None
        col['last'] = None
        self.col = col
        self.total_items = 0
        self.first = None
        self.last = None
        self.store_id = store_id
        self.db = db
        self.JSON_document_class = JSON_document_class

    def restore_from_json(self, col_json, page_docs):
        """ Restore from JSON
        """

        self.col = json.loads(col_json, object_pairs_hook=OrderedDict)
        for pd in page_docs:
            page = ASCollectionPage(None, pd.id, self.db,
                                    self.JSON_document_class) # BAD
            page.from_json(pd.json_string)
            self.add(page)

    def get(self, key):
        return self.col[key]

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
        """ Update self.col dict from member values.
        """

        self.col['first'] = self.first.get('id')
        self.col['last'] = self.last.get('id')
        self.col['totalItems'] = self.total_items

    def get_dict(self):
        """ Return the Collection as a Python dict.
        """

        return self.col

    def get_json(self):
        """ Return the Collection as JSON.
        """

        return json.dumps(self.col)

    def store(self):
        json_doc = self.JSON_document_class.query.filter_by(
                                                      id=self.store_id).first()
        if json_doc:
            json_doc.json_string = self.get_json()
            self.db.session.commit()
        else:
            json_doc = self.JSON_document_class(id=self.store_id,
                                                access_token='',
                                                json_string=self.get_json())
            self.db.session.add(json_doc)
            self.db.session.commit()


class ASCollectionPage():

    def __init__(self, ld_id, store_id, db, JSON_document_class):
        """ Create an empty CollectionPage.
        """

        cop = OrderedDict()
        cop['@context'] = 'https://www.w3.org/ns/activitystreams'
        cop['type'] = 'CollectionPage'
        cop['id'] = ld_id
        cop['summary'] = ('Activities generated based on the creation of one '
                          'Curation')
        cop['partOf'] = None
        # cop['prev']
        # cop['next']
        cop['items'] = []
        self.cop = cop
        self.part_of = None
        self.prev = None
        self.next = None
        self.store_id = store_id
        self.db = db
        self.JSON_document_class = JSON_document_class

    def from_json(self, json_str):
        self.cop = json.loads(json_str, object_pairs_hook=OrderedDict)
        self.part_of = self.cop['partOf']
        if self.cop.get('prev'):
            self.prev = self.cop['prev']
        if self.cop.get('next'):
            self.next = self.cop['next']

    def get(self, key):
        return self.cop[key]

    def set_part_of(self, col):
        self.part_of = col
        self.cop['partOf'] = self.part_of.get('id')
        self.store()

    def set_prev(self, other):
        self.prev = other
        if self.prev:
            self.cop['prev'] = self.prev.get('id')
        else:
            self.cop.pop('prev', None)
        self.store()

    def set_next(self, other):
        self.next = other
        if self.next:
            self.cop['next'] = self.next.get('id')
        else:
            self.cop.pop('next', None)
        self.store()

    def end_time(self):
        """ Return the latest time any of the contained Activity ended.
        """

        latest = datetime.datetime.fromtimestamp(0)
        for itm in self.cop['items']:
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

        self.cop['items'].append(activity)
        self.store()

    def get_dict(self):
        """ Return the CollectionPage as a Python dict.
        """

        return self.cop

    def get_json(self):
        """ Return the CollectionPage as JSON.
        """

        return json.dumps(self.cop)

    def store(self):
        json_doc = self.JSON_document_class.query.filter_by(
                                                      id=self.store_id).first()
        if json_doc:
            json_doc.json_string = self.get_json()
            self.db.session.commit()
        else:
            json_doc = self.JSON_document_class(id=self.store_id,
                                                access_token='',
                                                json_string=self.get_json())
            self.db.session.add(json_doc)
            self.db.session.commit()


class ActivityBuilder():

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
