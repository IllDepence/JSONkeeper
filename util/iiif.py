""" Classes for handling IIIF resources.
"""

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
                           ('http://codh.rois.ac.jp/iiif/curation/1/context.js'
                            'on')]
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
        """ Given a dict, see if it is a Manifest and if so, return the @id.

            Note: uses hard coded 'sc:' prefix instead of properly expanding
                  from a @context and checking.
        """

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

    def get_nth_range(self, n):
        """ Return the nth Range accross all selections or False if there is no
            nth Range and give it a @context.

            Note: n starts at 1!
        """

        ranges = self.cur['selections']

        if n <= len(ranges):
            r_idx = n - 1
            r_dict = OrderedDict()
            r_dict['@context'] = self.cur['@context']
            for key, val in ranges[r_idx].items():
                r_dict[key] = val
            return r_dict
        else:
            return False
