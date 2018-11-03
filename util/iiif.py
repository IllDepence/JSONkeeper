""" Classes for handling IIIF resources.
"""

import json
from collections import OrderedDict


class Curation():
    """ Very simple container for Curation documents (in the form of a
        dictionary) offering a few convenience metods.
    """

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

    def get_all_canvases(self, range_dict):
        """ Return (Manifest ID, Canvas ID) tuples for all Canvases across the
            Curation's Ranges.
        """

        cnvss = []
        for ran in self.cur['selections']:
            man_id = range_dict.get(ran['@id'])
            selector = False
            for candidate in ['canvases', 'members']:
                if candidate in ran.keys():
                    selector = candidate
            if selector:
                for can in ran[selector]:
                    if type(can) == str:
                        cnvss.append((man_id, can))
                    else:
                        cnvss.append((man_id, can['@id']))
        return cnvss

    def get_range_summary(self):
        """ Return a list as well as a dictionary for the
            Range--[within]-->Manifest relations contained in this Curation.
        """

        # Bad ad hoc spaghetti code ahead.
        #
        # Are Curation Ranges guaranteed to only have one value?
        # Is that value guaranteed to be a sc:Manifest (e.g. if no @type is
        #   given in a dictionary or if it's just a string)?
        # Can the value be a list containing the actual single value?
        # ↑ These questions have to be made clear to properly write this
        #   function.

        ret_lst = []
        ret_dic = {}
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
            elif type(w) == dict or type(w) == OrderedDict:
                mby_man = self._extract_manifest_id(w)
                if mby_man:
                    dic['man'] = mby_man
                else:
                    continue
            else:
                print(('WARNING: Can\'t parse a Range\'s within value.\n'
                       '>>> {}'.format(json.dumps(w))))
            ret_lst.append(dic)
            ret_dic[dic['ran']] = dic['man']
        return ret_lst, ret_dic

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
