#! /usr/bin/env python

##############################################################################
##  DendroPy Phylogenetic Computing Library.
##
##  Copyright 2010-2014 Jeet Sukumaran and Mark T. Holder.
##  All rights reserved.
##
##  See "LICENSE.txt" for terms and conditions of usage.
##
##  If you use this work or any portion thereof in published work,
##  please cite it as:
##
##     Sukumaran, J. and M. T. Holder. 2010. DendroPy: a Python library
##     for phylogenetic computing. Bioinformatics 26: 1569-1571.
##
##############################################################################

"""
Parsing of NEWICK-format tree from a stream.
"""

import re
import warnings
try:
    from StringIO import StringIO # Python 2 legacy support: StringIO in this module is the one needed (not io)
except ImportError:
    from io import StringIO # Python 3
from dendropy.datamodel import base
from dendropy.utility import error
from dendropy.dataio import tokenizer
from dendropy.dataio import nexusprocessing
from dendropy.dataio import ioservice

##############################################################################
## NewickReader

class NewickReader(ioservice.DataReader):
    """
    Parser for NEWICK-formatted data.
    """

    class NewickReaderError(error.DataParseError):
        def __init__(self, message,
                line_num=None,
                col_num=None,
                stream=None):
            error.DataParseError.__init__(self,
                    message=message,
                    line_num=line_num,
                    col_num=col_num,
                    stream=stream)

    class NewickReaderInvalidTokenError(NewickReaderError):
        def __init__(self,
                message,
                line_num=None,
                col_num=None,
                stream=None):
            NewickReader.NewickReaderError.__init__(self,
                    message=message,
                    line_num=line_num,
                    col_num=col_num,
                    stream=stream)

    class NewickReaderMalformedStatementError(NewickReaderError):
        def __init__(self,
                message,
                line_num=None,
                col_num=None,
                stream=None):
            NewickReader.NewickReaderError.__init__(self,
                    message=message,
                    line_num=line_num,
                    col_num=col_num,
                    stream=stream)

    class NewickReaderIncompleteTreeStatementError(NewickReaderMalformedStatementError):
        def __init__(self,
                message,
                line_num=None,
                col_num=None,
                stream=None):
            NewickReader.NewickReaderMalformedStatementError.__init__(self,
                    message=message,
                    line_num=line_num,
                    col_num=col_num,
                    stream=stream)


    class NewickReaderInvalidValueError(NewickReaderError):
        def __init__(self,
                message,
                line_num=None,
                col_num=None,
                stream=None):
            NewickReader.NewickReaderError.__init__(self,
                    message=message,
                    line_num=line_num,
                    col_num=col_num,
                    stream=stream)

    def __init__(self, **kwargs):
        """
        Keyword Arguments
        -----------------
        rooting : string, {['default-unrooted'], 'default-rooted', 'force-unrooted', 'force-rooted'}
            Specifies how trees in the data source should be intepreted with
            respect to their rooting:

                '``default-unrooted``' [default]:
                    All trees are interpreted as unrooted unless a '``[&R]``'
                    comment token explicitly specifies them as rooted.
                '``default-rooted``'
                    All trees are interpreted as rooted unless a '``[&U]``'
                    comment token explicitly specifies them as unrooted.
                '``force-unrooted``'
                    All trees are unconditionally interpreted as unrooted.
                '``force-rooted``'
                    All trees are unconditionally interpreted as rooted.

        edge_len_type : type, default: `float`
            Specifies the type of the edge lengths (`int` or `float`). Tokens
            interpreted as branch lengths will be cast to this type.
            Defaults to `float`.
        suppress_edge_lengths : boolean, default: `False`
            If `True`, edge length values will not be processed. If `False`,
            edge length values will be processed.
        extract_comment_metadata : boolean, default: `False`
            If `True`, any comments that begin with '&' or '&&' will be parsed
            and stored as part of the annotation set of the corresponding
            object (accessible through the `annotations` attribute of the
            object). This requires that the comment contents conform to
            a particular format (NHX or BEAST: 'field = value'). If `False`,
            then the comments will not be parsed, but will be instead stored
            directly as elements of the `comments` list attribute of the
            associated object.
        store_tree_weights : boolean, default: `False`
            If `True`, process the tree weight (e.g. "``[&W 1/2]``") comment
            associated with each tree, if any. Defaults to `False`.
        encode_splits : boolean, default: `False`
            If `True`, split hash bitmasks will be calculated and attached to
            the edges.
        finish_node_func : function object, default: `None`
            If specified, this function will be applied to each node after
            it has been constructed.
        case_sensitive_taxon_labels : boolean, default: `False`
            If `True`, then taxon labels are case sensitive (e.g., "``P.regius``"
            and "``P.REGIUS``" wil be treated as different operation taxonomic
            unit concepts). Otherwise, taxon label intepretation will be made
            without regard for case.
        preserve_underscores : boolean, default: `False`
            If `True`, unquoted underscores in labels will *not* converted to
            spaces. Defaults to `False`: all underscores not protected by
            quotes will be converted to spaces.
        suppress_internal_node_taxa : boolean, default: `True`
            If `False`, internal node labels will be instantantiated into
            :class:`Taxon` objects. If `True`, internal node labels
            will *not* be instantantiated as strings.
        suppress_external_node_taxa : boolean, default: `False`
            If `False`, external node labels will be instantantiated into
            :class:`Taxon` objects. If `True`, external node labels
            will *not* be instantantiated as strings.
        allow_duplicate_taxon_labels : boolean, default: `False`
            If `True`, then multiple identical taxon labels will be allowed.
            Defaults to `False`: treat multiple identical taxon labels as an
            error.
        """

        self._rooting = None
        ## (TEMPORARY and UGLY!!!!) Special handling for legacy signature
        if "as_unrooted" in kwargs or "as_rooted" in kwargs or "default_as_rooted" in kwargs or "default_as_unrooted" in kwargs:
            import collections
            legacy_kw = ("as_unrooted", "as_rooted", "default_as_rooted", "default_as_unrooted")
            legacy_kw_str = ", ".join("'{}'".format(k) for k in legacy_kw)
            if "rooting" in kwargs:
                raise ValueError("Cannot specify 'rooting' keyword argument in conjunction with any of the (legacy) keyword arguments ({}). Use 'rooting' alone.".format(legacy_kw_str))
            specs = collections.Counter(k for k in kwargs.keys() if k in legacy_kw)
            if sum(specs.values()) > 1:
                raise ValueError("Cannot specify more than one of {{ {} }} at the same time".format(legacy_kw_str))
            kw = list(specs.keys())[0]
            if kw == "as_unrooted":
                if kwargs[kw]:
                    corrected = "force-unrooted"
                else:
                    corrected = "force-rooted"
            elif kw == "as_rooted":
                if kwargs[kw]:
                    corrected = "force-rooted"
                else:
                    corrected = "force-unrooted"
            elif kw == "default_as_unrooted":
                if kwargs[kw]:
                    corrected = "default-unrooted"
                else:
                    corrected = "default-rooted"
            elif kw == "default_as_rooted":
                if kwargs[kw]:
                    corrected = "default-rooted"
                else:
                    corrected = "default-unrooted"
            msg = StringIO()
            error.dump_stack(msg)
            warnings.warn("\n{}\nUse of keyword argument '{}={}' is deprecated; use 'rooting=\"{}\"' instead".format(msg.getvalue(), kw, kwargs[kw], corrected),
                    FutureWarning, stacklevel=4)
            kwargs.pop(kw)
            kwargs["rooting"] = corrected
        self.rooting = kwargs.pop("rooting", "default-unrooted")
        self.edge_len_type = kwargs.pop("edge_len_type", float)
        self.suppress_edge_lengths = kwargs.pop("suppress_edge_lengths", False)
        self.extract_comment_metadata = kwargs.pop('extract_comment_metadata', False)
        self.store_tree_weights = kwargs.pop("store_tree_weights", False)
        self.encode_splits = kwargs.pop("encode_splits", False)
        self.finish_node_func = kwargs.pop("finish_node_func", None)
        self.case_sensitive_taxon_labels = kwargs.pop('case_sensitive_taxon_labels', False)
        self.preserve_underscores = kwargs.pop('preserve_underscores', False)
        self.suppress_internal_node_taxa = kwargs.pop("suppress_internal_node_taxa", True)
        self.suppress_external_node_taxa = kwargs.pop("suppress_external_node_taxa", False)
        self.allow_duplicate_taxon_labels = kwargs.pop("allow_duplicate_taxon_labels", False)
        if kwargs:
            raise TypeError("Unrecognized or unsupported arguments: {}".format(kwargs))
        self.tree_statement_complete = None

    def tree_iter(self,
            stream,
            taxon_symbol_mapper,
            tree_factory):
        """
        Iterator that yields trees in NEWICK-formatted source.

        Parameters
        ----------
        stream : file or file-like object
            A file or file-like object opened for reading.
        taxon_namespace : :class:`TaxonNamespace`
            Operational taxonomic unit namespace to use for taxon management.
        tree_factory : function object
            A function that returns a new :class:`Tree` object when called
            without arguments.

        Returns
        -------
        iter : :py:class:`collections.Iterator` [:class:`Tree`]
            An iterator yielding :class:`Tree` objects constructed based on
            data in `stream`.
        """
        nexus_tokenizer = nexusprocessing.NexusTokenizer(stream)
        while True:
            tree = self._parse_tree_statement(
                    nexus_tokenizer=nexus_tokenizer,
                    tree_factory=tree_factory,
                    taxon_symbol_map_func=taxon_symbol_mapper.require_taxon_for_symbol)
            yield tree
            if tree is None:
                raise StopIteration

    def _read(self,
            stream,
            taxon_namespace_factory=None,
            tree_list_factory=None,
            char_matrix_factory=None,
            global_annotations_target=None):
        taxon_namespace = taxon_namespace_factory(label=None)
        tree_list = tree_list_factory(label=None, taxon_namespace=taxon_namespace)
        taxon_symbol_mapper = nexusprocessing.NexusTaxonSymbolMapper(taxon_namespace=taxon_namespace,
                enable_lookup_by_taxon_number=False)
        tree_factory = tree_list.new_tree
        for tree in self.tree_iter(stream=stream,
                taxon_symbol_mapper=taxon_symbol_mapper,
                tree_factory=tree_factory):
            pass
        product = self.Product(
                taxon_namespaces=None,
                tree_lists=[tree_list],
                char_matrices=None)
        return product

    def _get_rooting(self):
        """
        Get rooting interpretation configuration.
        """
        return self._rooting
    def _set_rooting(self, val):
        """
        Set rooting interpretation configuration.
        """
        if val not in ("force-unrooted", "force-rooted", "default-unrooted", "default-rooted", None,):
            raise ValueError("Unrecognized rooting directive: '{}'".format(val))
        self._rooting = val
    rooting = property(_get_rooting, _set_rooting)

    def _parse_tree_statement(self,
            nexus_tokenizer,
            tree_factory,
            taxon_symbol_map_func):
        """
        Parses a single tree statement from a token stream and constructs a
        corresponding Tree object. Expects that the first non-comment and
        non-semi-colon token to be found, including the current token, to be
        the parenthesis that opens the tree statement. When complete, the
        current token will be the token immediately following the semi-colon,
        if any.
        """
        current_token = nexus_tokenizer.current_token
        tree_comments = nexus_tokenizer.pull_captured_comments()
        while (current_token == ";" or current_token is None) and not nexus_tokenizer.is_eof():
            current_token = nexus_tokenizer.require_next_token()
            tree_comments = nexus_tokenizer.pull_captured_comments()
        if nexus_tokenizer.is_eof():
            return None
        if current_token != "(":
            raise NewickReader.NewickReaderInvalidTokenError(
                    message="Expecting '{}' but found '{}'".format("(", current_token),
                    line_num=nexus_tokenizer.token_line_num,
                    col_num=nexus_tokenizer.token_column_num,
                    stream=nexus_tokenizer.src)
        tree = tree_factory()
        self._process_tree_comments(tree, tree_comments)
        self.tree_statement_complete = False
        self._parse_tree_node_description(
                nexus_tokenizer=nexus_tokenizer,
                tree=tree,
                current_node=tree.seed_node,
                taxon_symbol_map_func=taxon_symbol_map_func,
                is_internal_node=None)
        current_token = nexus_tokenizer.current_token
        if not self.tree_statement_complete:
            raise NewickReader.NewickReaderIncompleteTreeStatementError(
                    message="Incomplete or improperly-terminated tree statement (last character read was '{}' instead of a semi-colon ';')".format(nexus_tokenizer.current_token),
                    line_num=nexus_tokenizer.token_line_num,
                    col_num=nexus_tokenizer.token_column_num,
                    stream=nexus_tokenizer.src)
        while current_token == ";" and not nexus_tokenizer.is_eof():
            nexus_tokenizer.clear_captured_comments()
            current_token = nexus_tokenizer.next_token()
        return tree

    def _process_tree_comments(self, tree, tree_comments):
        # NOTE: this also unconditionally sets the tree rootedness and
        # weighting if no comment indicating these are found; for this to work
        # in the current implementation, this method must be called once and
        # exactly once per tree.
        rooting_token_found = False
        weighting_token_found = False
        for comment in tree_comments:
            if comment in ["&u", "&U", "&r", "&R"]:
                # print("\n\n**********\n**{}\n**{}\n*********".format(comment, self._parse_tree_rooting_state(comment)))
                tree.is_rooted = self._parse_tree_rooting_state(comment)
                rooting_token_found = True
            elif comment.startswith("&W") or comment.startswith("&w"):
                weighting_token_found = True
                if self.store_tree_weights:
                    try:
                        weight_expression = stream_tokenizer.tree_weight_comment.split(' ')[1]
                        tree.weight = eval("/".join(["float(%s)" % cv for cv in weight_expression.split('/')]))
                    except IndexError:
                        pass
                    except ValueError:
                        pass
                else:
                    # if tree weight comment is not processed,
                    # just store it
                    tree.comments.append(comment)
            elif self.extract_comment_metadata and comment.startswith("&"):
                annotations = self._parse_comment_metadata(comment)
                if annotations:
                    tree.annotations.update(annotations)
                else:
                    tree.comments.append(comment)
            else:
                tree.comments.append(comment)
        if not rooting_token_found:
            tree.is_rooted = self._parse_tree_rooting_state("")
        if self.store_tree_weights and not weighting_token_found:
            tree.weight = 1.0

    def _parse_tree_rooting_state(self, rooting_comment=None):
        """
        Returns rooting state for tree with given rooting comment token, taking
        into account `rooting` configuration.
        """
        if self._rooting == "force-unrooted":
            return False
        elif self._rooting == "force-rooted":
            return True
        elif rooting_comment == "&R" or rooting_comment == "&r":
            return True
        elif rooting_comment == "&U" or rooting_comment == "&u":
            return False
        elif self._rooting == "default-rooted":
            return True
        elif self._rooting == "default-unrooted":
            return False
        elif self._rooting is None:
            return None
        else:
            raise TypeError("Unrecognized rooting directive: '{}'".format(self._rooting))

    def _parse_tree_node_description(
            self,
            nexus_tokenizer,
            tree,
            current_node,
            taxon_symbol_map_func,
            is_internal_node=None):
        """
        Assuming that the iterator is currently sitting on a parenthesis
        that opens a node with children or the label of a leaf node, this
        will populate the node ``node`` appropriately (label, edge length,
        comments, metadata etc.) and recursively parse and add the node's
        children. When complete, the token will be the token immediately
        following the end of the node or tree statement if this is the root
        node, i.e. the token following the closing parenthesis of the node
        semi-colon terminating a tree statement.
        """
        current_node_comments = nexus_tokenizer.pull_captured_comments()
        if nexus_tokenizer.current_token == "(":
            nexus_tokenizer.require_next_token()
            node_created = False
            while True:
                if nexus_tokenizer.current_token == ",":
                    if not node_created: #184
                        # no node has been created yet: ',' designates a
                        # preceding blank node
                        new_node = tree.node_factory()
                        self._process_node_comments(node=new_node,
                                node_comments=nexus_tokenizer.pull_captured_comments())
                        self._finish_node(new_node)
                        current_node.add_child(new_node)
                        ## node_created = True # do not flag node as created to allow for an extra node to be created in the event of (..,)
                    nexus_tokenizer.require_next_token()
                    while nexus_tokenizer.current_token == ",": #192
                        # another blank node
                        new_node = tree.node_factory()
                        self._process_node_comments(node=new_node,
                                node_comments=nexus_tokenizer.pull_captured_comments())
                        self._finish_node(new_node)
                        current_node.add_child(new_node)
                        # node_created = True; # do not flag node as created: extra node needed in the event of (..,)
                        nexus_tokenizer.require_next_token()
                    if not node_created and nexus_tokenizer.current_token == ")": #200
                        # end of node
                        new_node = tree.node_factory();
                        self._process_node_comments(node=new_node,
                                node_comments=nexus_tokenizer.pull_captured_comments())
                        self._finish_node(new_node)
                        current_node.add_child(new_node)
                        node_created = True;
                elif nexus_tokenizer.current_token == ")": #206
                    # end of child nodes
                    nexus_tokenizer.require_next_token()
                    break
                else: #210
                    # assume child nodes: a leaf node (if a label) or
                    # internal (if a parenthesis)
                    if nexus_tokenizer.current_token == "(":
                        is_new_internal_node = True
                    else:
                        is_new_internal_node = False
                    new_node = tree.node_factory();
                    self._process_node_comments(node=new_node,
                            node_comments=nexus_tokenizer.pull_captured_comments())
                    self._parse_tree_node_description(
                            nexus_tokenizer=nexus_tokenizer,
                            tree=tree,
                            current_node=new_node,
                            taxon_symbol_map_func=taxon_symbol_map_func,
                            is_internal_node=is_new_internal_node,
                            )
                    current_node.add_child(new_node);
                    node_created = True;
        label_parsed = False
        self.tree_statement_complete = False
        if is_internal_node is None:
            # Initial call using `seed_node` does not set `is_internal_node` to
            # `True` or `False`, explicitly, but rather `None`. If this is the
            # case, the rest of the tree has be constructed, and we simply look
            # at whether there are children or not to determine if it is an
            # internal node. This approach allows for a single-tip tree.
            if current_node._child_nodes:
                is_internal_node = True
        while True:
            current_node_comments.extend(nexus_tokenizer.pull_captured_comments())
            if nexus_tokenizer.current_token == ":": #246
                nexus_tokenizer.require_next_token()
                if not self.suppress_edge_lengths:
                    try:
                        edge_length = self.edge_len_type(nexus_tokenizer.current_token)
                    except ValueError:
                        raise NewickReader.NewickReaderMalformedStatementError(
                                message="Invalid edge length: '{}'".format(nexus_tokenizer.current_token),
                                line_num=nexus_tokenizer.token_line_num,
                                col_num=nexus_tokenizer.token_column_num,
                                stream=nexus_tokenizer.src)
                    current_node.edge.length = edge_length
                nexus_tokenizer.require_next_token()
            elif nexus_tokenizer.current_token == ")": #253
                # closing of parent token
                self._process_node_comments(node=current_node,
                        node_comments=current_node_comments)
                self._finish_node(current_node)
                return current_node
            elif nexus_tokenizer.current_token == ";": #256
                # end of tree statement
                self.tree_statement_complete = True
                nexus_tokenizer.next_token()
                break
            elif nexus_tokenizer.current_token == ",": #260
                # end of this node
                self._process_node_comments(node=current_node,
                            node_comments=current_node_comments)
                self._finish_node(current_node)
                return current_node
            elif nexus_tokenizer.current_token == "(": #263
                # start of another node or tree without finishing this
                # node
                raise NewickReader.NewickReaderMalformedStatementError(
                        message="Malformed tree statement",
                        line_num=nexus_tokenizer.token_line_num,
                        col_num=nexus_tokenizer.token_column_num,
                        stream=nexus_tokenizer.src)
            else: #267
                # label
                if label_parsed: #269
                    raise NewickReader.NewickReaderMalformedStatementError(
                            message="Expecting ':', ')', ',' or ';' after reading label but found '{}'".format(nexus_tokenizer.current_token),
                            line_num=nexus_tokenizer.token_line_num,
                            col_num=nexus_tokenizer.token_column_num,
                            stream=nexus_tokenizer.src)
                else:
                    # Label
                    if not self.preserve_underscores and not nexus_tokenizer.is_token_quoted:
                        label = nexus_tokenizer.current_token.replace("_", " ")
                    else:
                        label = nexus_tokenizer.current_token
                    if ( (is_internal_node and self.suppress_internal_node_taxa)
                            or ((not is_internal_node) and self.suppress_external_node_taxa) ):
                        current_node.label = label
                    else:
                        current_node.taxon = taxon_symbol_map_func(label)
                    label_parsed = True;
                    nexus_tokenizer.require_next_token()
                    # try:
                    #     nexus_tokenizer.require_next_token()
                    # except tokenizer.Tokenizer.UnexpectedEndOfStreamError:
                    #     ## one possibility is that we have a single line
                    #     ## tree string with no terminating semi-colon ...
                    #     break
        ## if we are here, we have reached the end of the tree
        self._process_node_comments(node=current_node,
            node_comments=current_node_comments)
        self._finish_node(current_node)
        return current_node

    def _parse_comment_metadata(
            self,
            comment,
            annotations=None,
            field_name_map=None,
            field_value_types=None,
            strip_leading_trailing_spaces=True):
        """
        Returns set of :class:`Annotation` objects corresponding to metadata
        given in comments.

        Parameters
        ----------
        `comment` : string
            A comment token.
        `annotations` : :class:`AnnotationSet` or `set`
            Set of :class:`Annotation` objects to which to add this annotation.
        `field_name_map` : dict
            A dictionary mapping field names (as given in the comment string)
            to strings that should be used to represent the field in the
            metadata dictionary; if not given, no mapping is done (i.e., the
            comment string field name is used directly).
        `field_value_types` : dict
            A dictionary mapping field names (as given in the comment
            string) to the value type (e.g. {"node-age" : float}).
        `strip_leading_trailing_spaces` : boolean
            Remove whitespace from comments.

        Returns
        -------
        metadata : :py:class::`set` [:class:`Annotation`]
            Set of :class:`Annotation` objects corresponding to metadata
            parsed.
        """
        return nexusprocessing.parse_comment_metadata_to_annotations(
            comment=comment,
            annotations=annotations,
            field_name_map=field_name_map,
            field_value_types=field_value_types,
            strip_leading_trailing_spaces=strip_leading_trailing_spaces)


    def _process_node_comments(self, node, node_comments):
        for comment in node_comments:
            if self.extract_comment_metadata and comment.startswith("&"):
                annotations = self._parse_comment_metadata(comment)
                if annotations:
                    node.annotations.update(annotations)
                else:
                    node.comments.append(comment)
            else:
                node.comments.append(comment)

    def _finish_node(self, node):
        if self.finish_node_func is not None:
            self.finish_node_func(node)
