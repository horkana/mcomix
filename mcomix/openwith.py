""" openwith.py - Logic and storage for Open with... commands. """
import os.path
import gtk
import gobject

from mcomix.preferences import prefs


class OpenWithManager(object):
    def __init__(self):
        """ Constructor. """
        pass

    def set_commands(self, cmds):
        prefs['openwith commands'] = [(cmd.get_label(), cmd.get_command())
            for cmd in cmds]

    def get_commands(self):
        return [OpenWithCommand(label, command)
                for label, command in prefs['openwith commands']]

class OpenWithException(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)

class OpenWithCommand(object):
    def __init__(self, label, command):
        self.label = label
        if isinstance(command, str):
            self.command = command.decode('utf-8')
        else:
            self.command = command

    def get_label(self):
        return self.label

    def get_command(self):
        return self.command

    def execute(self, window):
        pass

    def validate(self):
        pass

    def parse(self, window):
        """ Parses the command string and replaces special characters
        with their respective variable contents. Returns a list of
        arguments. """
        command = os.path.expandvars(self.get_command())
        args = self._commandline_to_arguments(command, window)
        return args

    def _commandline_to_arguments(self, line, window):
        result = []
        buf = u""
        quote = False
        escape = False
        for c in line:
            if escape:
                if c == '%' or c == '"':
                    buf += c
                else:
                    buf += self._expand_variable(c, window)
                escape = False
            elif c == ' ':
                if quote:
                    buf += c
                elif len(buf) != 0:
                    result.append(buf)
                    buf = ""
            elif c == '"':
                if quote:
                    result.append(buf)
                    buf = ""
                    quote = False
                else:
                    quote = True
            elif c == '%':
                escape = True
            else:
                buf += c
        if escape:
            raise OpenWithException("Incomplete escape sequence")
        if quote:
            raise OpenWithException("Incomplete quotation")
        if len(buf) != 0:
            result.append(buf)
        return result

    def _expand_variable(self, identifier, window):
        if identifier == '/':
            return os.path.sep
        elif identifier == 'a':
            if window.filehandler.archive_type is None:
                raise OpenWithException("Not inside an archive")
            return window.filehandler.get_base_filename()
        elif identifier == 'f':
            return window.imagehandler.get_page_filename()
        elif identifier == 'w':
            if window.filehandler.archive_type is None:
                return os.path.basename(window.filehandler.get_path_to_base())
            else:
                return os.path.basename(os.path.dirname(window.filehandler.get_path_to_base()))
        elif identifier == 'A':
            return window.filehandler.get_path_to_base()
        elif identifier == 'D':
            return window.filehandler.get_path_to_base()
        elif identifier == 'F':
            return window.imagehandler.get_path_to_page()
        elif identifier == 'W':
            if window.filehandler.archive_type is None:
                return window.filehandler.get_path_to_base()
            else:
                return os.path.dirname(window.filehandler.get_path_to_base())
        else:
            raise OpenWithException("Invalid escape sequence");

class OpenWithEditor(gtk.Dialog):
    """ The editor for changing and creating external commands. This window
    keeps its own internal model once initialized, and will overwrite
    the external model (i.e. preferences) only when properly closed. """

    def __init__(self, window):
        gtk.Dialog.__init__(self, _('Edit external commands'), parent=window)
        self.set_destroy_with_parent(True)
        self._window = window
        self._openwith = OpenWithManager()

        self._command_tree = gtk.TreeView()
        self._command_tree.get_selection().connect('changed', self._item_selected)
        self._add_button = gtk.Button(stock=gtk.STOCK_ADD)
        self._add_button.connect('clicked', self._add_command)
        self._remove_button = gtk.Button(stock=gtk.STOCK_REMOVE)
        self._remove_button.connect('clicked', self._remove_command)
        self._remove_button.set_sensitive(False)
        self._info_label = gtk.Label()
        self._info_label.set_markup(
            '<b>' + _('Variables:') + '</b>\n' +
            _('<b>%f</b> - Filename') + '\n' +
            _('<b>%d</b> - Directory') + '\n')
        self._info_label.set_alignment(0, 0)
        self._test_button = gtk.Button(_('_Preview'))
        self._test_button.connect('clicked', self._test_command)
        self._test_field = gtk.Entry()
        self._test_field.set_property('editable', gtk.FALSE)
        self._test_field.set_text(_('Preview area'))

        self._layout()
        self._setup_table()
        self.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_CLOSE)
        self.set_default_response(gtk.RESPONSE_CLOSE)

        self.connect('response', self._response)

        self.resize(600, 300)
        self.show_all()

    def save(self):
        """ Serializes the tree model into a list of OpenWithCommands
        and passes these back to the Manager object for persistance. """
        model = self._command_tree.get_model()
        iter = model.get_iter_first()
        commands = []
        while iter:
            label, command = model.get(iter, 0, 1)
            commands.append(OpenWithCommand(label, command))
            iter = model.iter_next(iter)

        self._openwith.set_commands(commands)

    def _add_command(self, button):
        """ Add a new empty label-command line to the list. """
        self._command_tree.get_model().append((_('Command label'), _('Command')))

    def _remove_command(self, button):
        """ Removes the currently selected command from the list. """
        model, iter = self._command_tree.get_selection().get_selected()
        if (iter and model.iter_is_valid(iter)):
            model.remove(iter)

    def _test_command(self, button):
        """ Parses the currently selected command and displays the output in the
        text box next to the button. """
        if not self._window.filehandler.file_loaded:
            self._test_field.set_text(_('No file loaded. Preview not available.'))
            return

        model, iter = self._command_tree.get_selection().get_selected()
        if (iter and model.iter_is_valid(iter)):
            command = OpenWithCommand(*model.get(iter, 0, 1))
            def quote_if_necessary(arg):
                if u" " in arg:
                    return u'"' + arg.replace(u'"', u'\\"') + u'"'
                else:
                    return arg
            try:
                args = map(quote_if_necessary, command.parse(self._window))
                self._test_field.set_text(" ".join(args))
            except OpenWithException, e:
                self._test_field.set_text(unicode(e))

    def _item_selected(self, selection):
        """ Enable or disable buttons that depend on an item being selected. """
        for button in (self._remove_button, self._test_button):
            button.set_sensitive(selection.count_selected_rows() > 0)

    def _layout(self):
        """ Create and lay out UI components. """
        upperbox = gtk.HBox()
        self.get_content_area().pack_start(upperbox, padding=4)

        buttonbox = gtk.VBox()
        buttonbox.pack_start(self._add_button, False)
        buttonbox.pack_start(self._remove_button, False)
        buttonbox.pack_start(self._test_button, False)
        buttonbox.pack_end(self._info_label, padding=6)

        treebox = gtk.VBox()
        treebox.pack_start(self._command_tree, padding=4)
        treebox.pack_end(self._test_field, False)

        upperbox.pack_start(treebox, padding=4)
        upperbox.pack_end(buttonbox, False, padding=4)

    def _setup_table(self):
        """ Initializes the TreeView with settings and data. """
        for i, label in enumerate(('Label', 'Command')):
            renderer = gtk.CellRendererText()
            renderer.set_property('editable', gtk.TRUE)
            renderer.connect('edited', self._value_changed, i)
            column = gtk.TreeViewColumn(label, renderer)
            column.set_property('resizable', gtk.TRUE)
            column.set_attributes(renderer, text=i)
            self._command_tree.append_column(column)

        model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
        for command in self._openwith.get_commands():
            model.append((command.get_label(), command.get_command()))
        self._command_tree.set_model(model)

        self._command_tree.set_headers_visible(True)
        self._command_tree.set_reorderable(True)

    def _value_changed(self, renderer, path, new_text, column):
        """ Called when the user edits a field in the table. """
        iter = self._command_tree.get_model().get_iter(path)
        self._command_tree.get_model().set_value(iter, column, new_text)

    def _response(self, dialog, response):
        if response == gtk.RESPONSE_CLOSE:
            # TODO: Validate entries before saving
            self.save()
            self.hide_all()
            self.destroy()

# vim: expandtab:sw=4:ts=4
