"""
Unittests for opal.models
"""
import datetime
from mock import patch, MagicMock

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

from opal import models
from opal.core import exceptions
from opal.models import (
    Subrecord, Tagging, Team, Patient, InpatientAdmission, Symptom,
    SymptomComplex, UserProfile
)
from opal.core.test import OpalTestCase
import opal.tests.test_patient_lists # To make sure test tagged lists are pulled in
from opal.tests.models import (
    FamousLastWords, PatientColour, ExternalSubRecord, SymptomComplex, PatientConsultation,
    Birthday, DogOwner, HatWearer, HouseOwner
)

class PatientRecordAccessTestCase(OpalTestCase):

    def test_to_dict(self):
        patient = models.Patient.objects.create()
        access = models.PatientRecordAccess.objects.create(
            user=self.user, patient=patient)
        self.assertEqual(patient.id, access.to_dict(self.user)['patient'])
        self.assertEqual(self.user.username, access.to_dict(self.user)['username'])
        self.assertIsInstance(
            access.to_dict(self.user)['datetime'], datetime.datetime
        )


class PatientTestCase(OpalTestCase):

    @patch("opal.models.application.get_app")
    def test_created_with_the_default_episode(self, get_app):
        test_app = MagicMock()
        test_app.default_episode_category ="testcategory"
        get_app.return_value = test_app
        _, episode = self.new_patient_and_episode_please()
        self.assertEqual(episode.category_name, "testcategory")

    def test_create_episode_category(self):
        patient = models.Patient.objects.create()
        e = patient.create_episode(category_name='testcategory')
        self.assertEqual('testcategory', e.category_name)

    def test_bulk_update_patient_subrecords(self):
        original_patient = models.Patient()

        d = {
            "demographics": [{
                "first_name": "Samantha",
                "surname": "Sun",
                "hospital_number": "123312"
            }],
            "patient_colour": [
                {"name": "green"},
                {"name": "purple"},
            ]
        }
        original_patient.bulk_update(d, self.user)

        patient = Patient.objects.get()
        demographics = patient.demographics_set.get()
        self.assertEqual(demographics.first_name, "Samantha")
        self.assertEqual(demographics.surname, "Sun")
        self.assertEqual(demographics.hospital_number, "123312")

        colours = patient.patientcolour_set.all()
        self.assertEqual(len(colours), 2)
        self.assertEqual(colours[0].name, "green")
        self.assertEqual(colours[1].name, "purple")
        self.assertTrue(patient.episode_set.exists())

    def test_bulk_update_with_existing_patient_episode(self):
        original_patient = models.Patient()
        original_patient.save()
        original_episode = original_patient.create_episode()

        d = {
            "demographics": [{
                "first_name": "Samantha",
                "surname": "Sun",
                "hospital_number": "123312"
            }],
            "patient_colour": [
                {"name": "green"},
                {"name": "purple"},
            ]
        }
        original_patient.bulk_update(d, self.user)

        patient = Patient.objects.get()
        demographics = patient.demographics_set.get()
        self.assertEqual(demographics.first_name, "Samantha")
        self.assertEqual(demographics.surname, "Sun")
        self.assertEqual(demographics.hospital_number, "123312")

        colours = patient.patientcolour_set.all()
        self.assertEqual(len(colours), 2)
        self.assertEqual(colours[0].name, "green")
        self.assertEqual(colours[1].name, "purple")
        self.assertTrue(patient.episode_set.get(), original_episode)

    def test_bulk_update_without_demographics(self):
        original_patient = models.Patient()

        d = {
            "patient_colour": [
                {"name": "green"},
                {"name": "purple"},
            ]
        }

        original_patient.bulk_update(d, self.user)
        self.assertIsNone(original_patient.demographics_set.first().hospital_number)

    def test_bulk_update_tagging_ignored(self):
        original_patient = models.Patient()
        original_patient.save()

        d = {
            "demographics": [{
                "first_name": "Samantha",
                "surname": "Sun",
                "hospital_number": "123312"
            }],
            "tagging": [
                {"id": 1},
            ]
        }
        original_patient.bulk_update(d, self.user)
        episode = original_patient.episode_set.first()
        self.assertEqual(list(episode.get_tag_names(self.user)), [])

    def test_bulk_update_episode_subrecords_without_episode(self):
        original_patient = models.Patient()

        d = {
            "demographics": [{
                "first_name": "Samantha",
                "surname": "Sun",
                "hospital_number": "123312"
            }],
            "hat_wearer": [
                {"name": "bowler"},
                {"name": "wizard"},
            ],
            "location": [
                {
                    "ward": "a ward",
                    "bed": "a bed"
                },
            ]
        }
        self.assertFalse(models.Episode.objects.exists())
        original_patient.bulk_update(d, self.user)

        patient = Patient.objects.get()
        demographics = patient.demographics_set.get()
        self.assertEqual(demographics.first_name, "Samantha")
        self.assertEqual(demographics.surname, "Sun")
        self.assertEqual(demographics.hospital_number, "123312")
        self.assertEqual(models.Episode.objects.count(), 1)
        episode = patient.episode_set.get()

        hat_wearers = episode.hatwearer_set.all()
        self.assertEqual(len(hat_wearers), 2)
        self.assertEqual(hat_wearers[0].name, "bowler")
        self.assertEqual(hat_wearers[1].name, "wizard")
        self.assertEqual(hat_wearers[0].episode, episode)
        self.assertEqual(hat_wearers[1].episode, episode)

        location = episode.location_set.get()
        self.assertEqual(location.bed, "a bed")
        self.assertEqual(location.ward, "a ward")


class SubrecordTestCase(OpalTestCase):

    def test_get_display_name_from_property(self):
        self.assertEqual('Wearer of Hats', HatWearer.get_display_name())

    def test_date_time_deserialisation(self):
        patient, _ = self.new_patient_and_episode_please()
        birthday_date = "10/1/2000"
        birthday_party= "11/2/2016 20:30:10"
        birthday = Birthday()
        birthday.update_from_dict(dict(
            birth_date=birthday_date,
            party=birthday_party,
            patient_id=patient.id
        ), self.user)

        bday = Birthday.objects.get()
        self.assertEqual(bday.patient_id, patient.id)
        self.assertEqual(bday.birth_date, datetime.date(2000, 1, 10))
        # stip off miliseconds, we don't use them
        start = bday.party.isoformat()[:19]
        expected_start = '2016-02-11T20:30:10'
        self.assertEqual(start, expected_start)

    def test_display_template_does_not_exist(self):
        self.assertEqual(None, Subrecord.get_display_template())

    @patch('opal.models.find_template')
    def test_display_template(self, find):
        Subrecord.get_display_template()
        find.assert_called_with(['records/subrecord.html'])

    @patch('opal.models.find_template')
    def test_display_template_list(self, find):
        patient_list = MagicMock()
        patient_list.get_template_prefixes = MagicMock(return_value=["test"])
        Subrecord.get_display_template(patient_list=patient_list)
        find.assert_called_with([
            'records/test/subrecord.html',
            'records/subrecord.html',
        ])

    @patch('opal.models.find_template')
    def test_display_template_episode_type(self, find):
        Subrecord.get_display_template(episode_type='Inpatient')
        find.assert_called_with([
            'records/inpatient/subrecord.html',
            'records/subrecord.html',
        ])

    @patch('opal.models.find_template')
    def test_display_template_list_episode_type(self, find):
        with self.assertRaises(ValueError):
            Subrecord.get_display_template(
                patient_list='test', episode_type='Inpatient'
            )

    def test_detail_template_does_not_exist(self):
        self.assertEqual(None, Subrecord.get_detail_template())

    @patch('opal.models.find_template')
    def test_detail_template(self, find):
        Subrecord.get_detail_template()
        find.assert_called_with([
            'records/subrecord_detail.html',
            'records/subrecord.html'
        ])

    @patch('opal.models.find_template')
    def test_detail_template_list(self, find):
        Subrecord.get_detail_template(patient_list='test')
        find.assert_called_with([
            'records/subrecord_detail.html',
            'records/subrecord.html'
        ])

    @patch('opal.models.find_template')
    def test_detail_template_episode_type(self, find):
        Subrecord.get_detail_template(episode_type='Inpatient')
        find.assert_called_with([
            'records/inpatient/subrecord_detail.html',
            'records/inpatient/subrecord.html',
            'records/subrecord_detail.html',
            'records/subrecord.html'
        ])

    @patch('opal.models.find_template')
    def test_detail_template_list_episode_type(self, find):
        with self.assertRaises(ValueError):
            Subrecord.get_detail_template(episode_type='Inpatient', patient_list='test')

    def test_form_template_does_not_exist(self):
        self.assertEqual(None, Subrecord.get_form_template())

    @patch('opal.models.find_template')
    def test_form_template(self, find):
        Subrecord.get_form_template()
        find.assert_called_with(['forms/subrecord_form.html'])

    def test_get_form_url(self):
        url = Subrecord.get_form_url()
        self.assertEqual(url, '/templates/forms/subrecord.html')

    @patch('opal.models.find_template')
    def test_form_template_list(self, find):
        patient_list = MagicMock()
        patient_list.get_template_prefixes = MagicMock(return_value=["test"])
        Subrecord.get_form_template(patient_list=patient_list)
        find.assert_called_with([
            'forms/test/subrecord_form.html',
            'forms/subrecord_form.html'
        ])

    @patch('opal.models.find_template')
    def test_form_template_episode_type(self, find):
        Subrecord.get_form_template(episode_type='Inpatient')
        find.assert_called_with([
            'forms/inpatient/subrecord_form.html',
            'forms/subrecord_form.html'
        ])

    @patch('opal.models.find_template')
    def test_form_template_list_episode_type(self, find):
        with self.assertRaises(ValueError):
            Subrecord.get_form_template(episode_type='Inpatient', patient_list='test')

    def test_get_modal_template_does_not_exist(self):
        self.assertEqual(None, Subrecord.get_modal_template())

    @patch('opal.models.find_template')
    @patch('opal.models.Subrecord.get_form_template')
    def test_modal_template_no_form_template(self, modal, find):
        modal.return_value = None
        Subrecord.get_modal_template()
        find.assert_called_with(['modals/subrecord_modal.html'])

    @patch('opal.models.find_template')
    def test_modal_template_list(self, find):
        patient_list = MagicMock()
        patient_list.get_template_prefixes = MagicMock(return_value=["test"])
        Subrecord.get_modal_template(patient_list=patient_list)
        find.assert_called_with([
            'modals/test/subrecord_modal.html',
            'modals/subrecord_modal.html',
            'modal_base.html'
        ])

    @patch('opal.models.find_template')
    def test_modal_template_episode_type(self, find):
        Subrecord.get_modal_template(episode_type='Inpatient')
        find.assert_called_with([
            'modals/inpatient/subrecord_modal.html',
            'modals/subrecord_modal.html',
            'modal_base.html'
        ])

    @patch('opal.models.find_template')
    def test_modal_template_episode_type_list(self, find):
        with self.assertRaises(ValueError):
            Subrecord.get_modal_template(episode_type='Inpatient', patient_list='test')

    def test_get_normal_field_title(self):
        name_title = PatientColour._get_field_title("name")
        self.assertEqual(name_title, "Name")

    def test_get_foreign_key_or_free_text_title(self):
        dog_title = DogOwner._get_field_title("dog")
        self.assertEqual(dog_title, "Dog")

    def test_get_title_over_many_to_many(self):
        hats = HatWearer._get_field_title("hats")
        self.assertEqual(hats, "Hats")

    def test_get_title_over_reverse_foreign_key(self):
        hats = HouseOwner._get_field_title("house")
        self.assertEqual(hats, "Houses")

    def test_verbose_name(self):
        only_words = FamousLastWords._get_field_title("words")
        self.assertEqual(only_words, "Only Words")

    def test_verbose_name_abbreviation(self):
        # if a word is an abbreviation already, don't title case it!
        osd = DogOwner._get_field_title("ownership_start_date")
        self.assertEqual(osd, "OSD")


class BulkUpdateFromDictsTest(OpalTestCase):

    def test_bulk_update_from_dict(self):
        self.assertFalse(PatientColour.objects.exists())
        patient_colours = [
            {"name": "purple"},
            {"name": "blue"}
        ]
        patient = Patient.objects.create()
        PatientColour.bulk_update_from_dicts(
            patient, patient_colours, self.user
        )
        expected_patient_colours = set(["purple", "blue"])
        new_patient_colours = set(PatientColour.objects.values_list(
            "name", flat=True
        ))
        self.assertEqual(
            expected_patient_colours, new_patient_colours
        )


    def test_bulk_update_existing_from_dict(self):
        patient = Patient.objects.create()
        patient_colours = []
        for colour in ["green", "red"]:
            patient_colours.append(
                PatientColour.objects.create(patient=patient, name=colour)
            )
        patient_colours = [
            {"name": "purple", "id": patient_colours[0].id},
            {"name": "blue", "id": patient_colours[1].id}
        ]
        PatientColour.bulk_update_from_dicts(
            patient, patient_colours, self.user
        )
        expected_patient_colours = set(["purple", "blue"])
        new_patient_colours = set(PatientColour.objects.values_list(
            "name", flat=True
        ))
        self.assertEqual(
            expected_patient_colours, new_patient_colours
        )

    def test_bulk_update_multiple_singletons_from_dict(self):
        patient = Patient.objects.create()
        famous_last_words = [
            {"words": "so long and thanks for all the fish"},
            {"words": "A towel is the most important item"},
        ]

        with self.assertRaises(ValueError):
            FamousLastWords.bulk_update_from_dicts(
                patient, famous_last_words, self.user
            )

    def test_bulk_update_singleton(self):
        patient = Patient.objects.create()
        famous_model = FamousLastWords.objects.get()
        famous_model.set_consistency_token()
        famous_model.save()

        famous_last_words = [
            {"words": "A towel is the most important item"},
        ]

        with self.assertRaises(exceptions.APIError):
            FamousLastWords.bulk_update_from_dicts(
                patient, famous_last_words, self.user
            )

    def test_bulk_update_singleton_with_force(self):
        patient = Patient.objects.create()
        famous_model = FamousLastWords.objects.get()
        famous_model.set_consistency_token()
        famous_model.save()

        famous_last_words = [
            {"words": "A towel is the most important item"},
        ]

        FamousLastWords.bulk_update_from_dicts(
            patient, famous_last_words, self.user, force=True
        )

        result = FamousLastWords.objects.get()
        self.assertEqual(result.words, famous_last_words[0].values()[0])


class InpatientAdmissionTestCase(OpalTestCase):
    def test_updates_with_external_identifer(self):
        patient = models.Patient()
        patient.save()
        yesterday = timezone.make_aware(datetime.datetime.now() - datetime.timedelta(1))
        InpatientAdmission.objects.create(
            datetime_of_admission=yesterday,
            external_identifier="1",
            patient=patient
        )

        now = timezone.make_aware(datetime.datetime.now()).strftime(
            settings.DATETIME_INPUT_FORMATS[0]
        )

        update_dict = dict(
            datetime_of_admission=now,
            external_identifier="1",
            patient_id=patient.id
        )

        a = InpatientAdmission()
        a.update_from_dict(update_dict, self.user)

        result = InpatientAdmission.objects.get()
        self.assertEqual(
            result.datetime_of_admission.date(),
            datetime.date.today()
        )

    def test_no_external_identifier(self):
        patient = models.Patient()
        patient.save()
        yesterday = timezone.make_aware(datetime.datetime.now() - datetime.timedelta(1))
        InpatientAdmission.objects.create(
            datetime_of_admission=yesterday,
            external_identifier="1",
            patient=patient
        )

        now = datetime.datetime.now().strftime(
            settings.DATETIME_INPUT_FORMATS[0]
        )

        update_dict = dict(
            datetime_of_admission=now,
            patient_id=patient.id
        )

        a = InpatientAdmission()
        a.update_from_dict(update_dict, self.user)

        results = InpatientAdmission.objects.all()
        self.assertEqual(2, len(results))

        self.assertEqual(
            results[0].datetime_of_admission.date(),
            yesterday.date()
        )

        self.assertEqual(
            results[1].datetime_of_admission.date(),
            datetime.date.today()
        )

    def test_doesnt_update_empty_external_identifier(self):
        patient = models.Patient()
        patient.save()
        yesterday = timezone.make_aware(datetime.datetime.now() - datetime.timedelta(1))
        InpatientAdmission.objects.create(
            datetime_of_admission=yesterday,
            external_identifier="",
            patient=patient
        )

        now = datetime.datetime.now().strftime(
            settings.DATETIME_INPUT_FORMATS[0]
        )

        update_dict = dict(
            datetime_of_admission=now,
            external_identifier="",
            patient_id=patient.id
        )

        a = InpatientAdmission()
        a.update_from_dict(update_dict, self.user)

        results = InpatientAdmission.objects.all()
        self.assertEqual(2, len(results))

        self.assertEqual(
            results[0].datetime_of_admission.date(),
            yesterday.date()
        )

        self.assertEqual(
            results[1].datetime_of_admission.date(),
            datetime.date.today()
        )

    def test_doesnt_update_a_different_patient(self):
        other_patient = Patient.objects.create()
        patient = models.Patient()
        patient.save()
        yesterday = timezone.make_aware(datetime.datetime.now() - datetime.timedelta(1))
        InpatientAdmission.objects.create(
            datetime_of_admission=yesterday,
            external_identifier="1",
            patient=patient
        )

        now = datetime.datetime.now().strftime(
            settings.DATETIME_INPUT_FORMATS[0]
        )

        update_dict = dict(
            datetime_of_admission=now,
            external_identifier="",
            patient_id=other_patient.id
        )

        a = InpatientAdmission()
        a.update_from_dict(update_dict, self.user)

        results = InpatientAdmission.objects.all()
        self.assertEqual(2, len(results))

        self.assertEqual(
            results[0].datetime_of_admission.date(),
            yesterday.date()
        )

        self.assertEqual(
            results[1].datetime_of_admission.date(),
            datetime.date.today()
        )


class PatientConsultationTestCase(OpalTestCase):
    def setUp(self):
        _, self.episode = self.new_patient_and_episode_please()
        self.patient_consultation = PatientConsultation.objects.create(
            episode_id=self.episode.id
        )

    def test_if_when_is_set(self):
        when = datetime.datetime(2016, 06, 10, 12, 2, 20)
        patient_consultation_dict = dict(
            when='10/06/2016 12:02:20',
        )

        self.patient_consultation.update_from_dict(patient_consultation_dict, self.user)
        patient_consultation = self.episode.patientconsultation_set.first()
        self.assertEqual(patient_consultation.when.year, when.year)
        self.assertEqual(patient_consultation.when.month, when.month)
        self.assertEqual(patient_consultation.when.day, when.day)

    def test_if_when_is_not_set(self):
        now = timezone.now()
        patient_consultation_dict = dict()
        self.patient_consultation.update_from_dict(patient_consultation_dict, self.user)
        patient_consultation = self.episode.patientconsultation_set.first()
        self.assertTrue(patient_consultation.when >= now)


class SymptomComplexTestCase(OpalTestCase):
    def setUp(self):
        self.patient, self.episode = self.new_patient_and_episode_please()
        super(SymptomComplexTestCase, self).setUp()
        self.symptom_1 = Symptom.objects.create(name="tiredness")
        self.symptom_2 = Symptom.objects.create(name="alertness")
        self.symptom_3 = Symptom.objects.create(name="apathy")
        self.symptom_complex = SymptomComplex.objects.create(
            duration="a week",
            details="information",
            consistency_token=1111,
            episode=self.episode
        )
        self.symptom_complex.symptoms.add(self.symptom_2, self.symptom_3)

    def test_to_dict(self):
        expected_data = dict(
            id=self.symptom_complex.id,
            consistency_token=self.symptom_complex.consistency_token,
            symptoms=["alertness", "apathy"],
            duration="a week",
            details="information",
            episode_id=1,
            updated=None,
            updated_by_id=None,
            created=None,
            created_by_id=None
        )
        self.assertEqual(
            expected_data, self.symptom_complex.to_dict(self.user)
        )

    def test_update_from_dict(self):
        data = {
            u'consistency_token': self.symptom_complex.consistency_token,
            u'id': self.symptom_complex.id,
            u'symptoms': [u'alertness', u'tiredness'],
            u'duration': 'a month',
            u'details': 'other information'
        }
        self.symptom_complex.update_from_dict(data, self.user)
        new_symptoms = self.symptom_complex.symptoms.values_list(
            "name", flat=True
        )
        self.assertEqual(set(new_symptoms), set([u'alertness', u'tiredness']))
        self.assertEqual(self.symptom_complex.duration, 'a month')
        self.assertEqual(
            self.symptom_complex.details, 'other information'
        )


class TaggingTestCase(OpalTestCase):
    def test_display_template(self):
        self.assertEqual('tagging.html', Tagging.get_display_template())

    def test_form_template(self):
        self.assertEqual('tagging_modal.html', Tagging.get_form_template())

    def test_field_schema(self):
        names = ['eater', 'herbivore', 'carnivore']
        fields = [{'name': tagname, 'type': 'boolean'} for tagname in names]
        schema = Tagging.build_field_schema()
        for field in fields:
            self.assertIn(field, schema)


class TeamTestCase(OpalTestCase):

    def test_for_restricted_user(self):
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.restricted_only = True
        profile.save()
        self.assertEqual([], Team.for_user(self.user))

    def test_has_subteams(self):
        t = Team()
        self.assertEqual(False, t.has_subteams)



class AbstractDemographicsTestCase(OpalTestCase):
    def test_name(self):
        d = models.Demographics(first_name='Jane',
                                surname='Doe',
                                middle_name='Obsidian')
        self.assertEqual('Jane Doe', d.name)


class ExternalSystemTestCase(OpalTestCase):
    def test_get_footer(self):
        self.assertEqual(
            ExternalSubRecord.get_modal_footer_template(),
            "partials/_sourced_modal_footer.html"
        )
