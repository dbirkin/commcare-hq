from __future__ import absolute_import
from __future__ import unicode_literals
import polib
import datetime

from django.conf import settings
from memoized import memoized

from collections import namedtuple, OrderedDict
from corehq.apps.app_manager import id_strings

Translation = namedtuple('Translation', 'key translation occurrences')
Unique_ID = namedtuple('UniqueID', 'type id')


class POFileGenerator:
    def __init__(self, domain, app_id, version, key_lang, source_lang, lang_prefix):
        self.domain = domain
        self.app_id = app_id
        self.key_lang = key_lang
        self.source_lang = source_lang
        self.lang_prefix = lang_prefix
        self.translations = OrderedDict()
        self.version = version
        self.headers = dict()  # headers for each sheet name
        self.generated_files = list()
        self.sheet_name_to_module_or_form_type_and_id = dict()

    @property
    @memoized
    def app_id_to_build(self):
        return self._find_build_id()

    def _find_build_id(self):
        # find build id if version specified
        if self.version:
            from corehq.apps.app_manager.dbaccessors import get_all_built_app_ids_and_versions
            built_app_ids = get_all_built_app_ids_and_versions(self.domain, self.app_id)
            for app_built_version in built_app_ids:
                if app_built_version.version == self.version:
                    return app_built_version.build_id
            raise Exception("Build for version requested not found")
        else:
            return self.app_id

    def _translation_data(self, app):
        # get the translations data
        from corehq.apps.app_manager.app_translations.app_translations import expected_bulk_app_sheet_rows
        # simply the rows of data per sheet name
        rows = expected_bulk_app_sheet_rows(app)

        # get the translation data headers
        from corehq.apps.app_manager.app_translations.app_translations import expected_bulk_app_sheet_headers
        for header_row in expected_bulk_app_sheet_headers(app):
            self.headers[header_row[0]] = header_row[1]
        self._set_sheet_name_to_module_or_form_mapping(rows[u'Modules_and_forms'])
        return rows

    def _set_sheet_name_to_module_or_form_mapping(self, all_module_and_form_details):
        # iterate the first sheet to get unique ids for forms/modules
        sheet_name_column_index = self._get_header_index(u'Modules_and_forms', 'sheet_name')
        unique_id_column_index = self._get_header_index(u'Modules_and_forms', 'unique_id')
        type_column_index = self._get_header_index(u'Modules_and_forms', 'Type')
        for row in all_module_and_form_details:
            self.sheet_name_to_module_or_form_type_and_id[row[sheet_name_column_index]] = Unique_ID(
                row[type_column_index],
                row[unique_id_column_index]
            )

    def _get_filename(self, sheet_name):
        return sheet_name + '_v' + str(self.version)

    def _get_header_index(self, sheet_name, column_name):
        for index, _column_name in enumerate(self.headers[sheet_name]):
            if _column_name == column_name:
                return index
        raise Exception("Column not found with name {}".format(column_name))

    def _get_translation_for_sheet(self, app, sheet_name, rows):
        translations_for_sheet = OrderedDict()
        key_lang_index = self._get_header_index(sheet_name, self.lang_prefix + self.key_lang)
        source_lang_index = self._get_header_index(sheet_name, self.lang_prefix + self.source_lang)
        occurrences = []
        if sheet_name != u'Modules_and_forms':
            type_and_id = self.sheet_name_to_module_or_form_type_and_id[sheet_name]
            if type_and_id.type == "Module":
                ref_module = app.get_module_by_unique_id(type_and_id.id)
                occurrences = [(id_strings.module_locale(ref_module), '')]
            elif type_and_id.type == "Form":
                ref_form = app.get_form(type_and_id.id)
                occurrences = [(id_strings.form_locale(ref_form), '')]
        for row in rows:
            source = row[key_lang_index]
            translation = row[source_lang_index]
            if source not in translations_for_sheet:
                translations_for_sheet[source] = Translation(
                    source,
                    translation or source,  # to avoid blank msgstr in po file
                    [].extend(occurrences))
        return translations_for_sheet

    def _build_translations(self):
        """
        :return:
        {
            sheet_name_with_build_id: {
                key: Translation(key, translation, occurrences)
            }
        }
        """
        from corehq.apps.app_manager.dbaccessors import get_current_app
        app = get_current_app(self.domain, self.app_id_to_build)
        if self.version is None:
            self.version = app.version

        rows = self._translation_data(app)

        for sheet_name in rows:
            file_name = self._get_filename(sheet_name)
            self.translations[file_name] = self._get_translation_for_sheet(
                app, sheet_name, rows[sheet_name]
            )

    def generate_translation_files(self):
        self._build_translations()
        if settings.TRANSIFEX_DETAILS:
            team = settings.TRANSIFEX_DETAILS['teams'].get(self.key_lang)
        else:
            team = ""
        now = str(datetime.datetime.now())
        for file_name in self.translations:
            sheet_translations = self.translations[file_name]
            po = polib.POFile()
            po.check_for_duplicates = True
            po.metadata = {
                'App-Id': self.app_id_to_build,
                'PO-Creation-Date': now,
                'Language-Team': "{lang} ({team})".format(
                    lang=self.key_lang, team=team
                ),
                'MIME-Version': '1.0',
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Transfer-Encoding': '8bit',
                'Language': self.key_lang,
                'Version': self.version
            }

            for source in sheet_translations:
                if source:
                    translation = sheet_translations[source]
                    entry = polib.POEntry(
                        msgid=translation.key,
                        msgstr=translation.translation,
                        occurrences=translation.occurrences
                    )
                    po.append(entry)
            po.save(file_name)
            self.generated_files.append(file_name)