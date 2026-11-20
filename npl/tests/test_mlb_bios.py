"""Player-level MLB refresh: bios in, NPL club and stats left alone."""

import datetime
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from npl.mlb_bios import bio_values, merge_people, sync_bios
from npl.models import Player, Team


def major_leaguer(**overrides):
    person = {
        "id": 592450,
        "fullName": "Aaron Judge",
        "useName": "Aaron",
        "useLastName": "Judge",
        "firstName": "Aaron",
        "lastName": "Judge",
        "birthDate": "1992-04-26",
        "height": "6' 7\"",
        "weight": 282,
        "birthCountry": "USA",
        "mlbDebutDate": "2016-08-13",
        "active": True,
        "primaryPosition": {"abbreviation": "RF"},
        "batSide": {"code": "R"},
        "pitchHand": {"code": "R"},
        "currentTeam": {"id": 147},
    }
    person.update(overrides)
    return person


def minor_leaguer(**overrides):
    person = {
        "id": 800001,
        "fullName": "Kid Player",
        "useName": "Kid",
        "useLastName": "Player",
        "birthDate": "2004-04-02",
        "height": "6' 1\"",
        "weight": 195,
        "birthCountry": "Dominican Republic",
        "mlbDebutDate": None,
        "active": True,
        "primaryPosition": {"abbreviation": "P"},
        "batSide": {"code": "L"},
        "pitchHand": {"code": "R"},
        "currentTeam": {"id": 512},
    }
    person.update(overrides)
    return person


class BioValueTests(SimpleTestCase):
    def test_major_league_payload_fills_the_non_stat_fields(self):
        values = bio_values(major_leaguer(), sport_id=1, mlb_list_ok=True)
        self.assertEqual(values["name"], "Aaron Judge")
        self.assertEqual(values["first_name"], "Aaron")
        self.assertEqual(values["last_name"], "Judge")
        self.assertEqual(values["birthdate"], datetime.date(1992, 4, 26))
        self.assertEqual(values["height"], "6' 7\"")
        self.assertEqual(values["weight"], "282")
        self.assertEqual(values["position"], "RF")
        self.assertEqual(values["bats"], "R")
        self.assertEqual(values["throws"], "R")
        self.assertEqual(values["birth_country"], "USA")
        self.assertEqual(values["mlb_debut_date"], datetime.date(2016, 8, 13))
        self.assertTrue(values["has_appeared_in_majors"])
        self.assertTrue(values["active"])
        self.assertEqual(values["mlb_org"], "NYY")
        self.assertEqual(values["roster_status"], "MLB")

    def test_minor_league_org_comes_from_the_parent_club(self):
        values = bio_values(
            minor_leaguer(),
            sport_id=11,
            teams_by_id={512: {"id": 512, "parentOrgId": 116}},
            mlb_list_ok=True,
        )
        self.assertEqual(values["mlb_org"], "DET")
        self.assertEqual(values["roster_status"], "MINORS")
        self.assertFalse(values["has_appeared_in_majors"])
        self.assertIsNone(values["mlb_debut_date"])
        self.assertEqual(values["weight"], "195")

    def test_parent_org_on_the_person_is_enough(self):
        person = minor_leaguer(currentTeam={"id": 5482, "parentOrgId": 113})
        values = bio_values(person, sport_id=None, mlb_list_ok=True)
        self.assertEqual(values["mlb_org"], "CIN")
        self.assertEqual(values["roster_status"], "MINORS")

    def test_blank_measurements_are_left_out(self):
        values = bio_values(
            major_leaguer(height=None, weight=None, birthCountry="", primaryPosition={}),
            sport_id=1,
        )
        self.assertNotIn("height", values)
        self.assertNotIn("weight", values)
        self.assertNotIn("position", values)
        self.assertNotIn("birth_country", values)
        self.assertEqual(values["mlb_org"], "NYY")

    def test_todays_club_comes_from_the_people_payload(self):
        values = bio_values(major_leaguer(active=True), sport_id=None)
        self.assertEqual(values["mlb_org"], "NYY")
        self.assertEqual(values["roster_status"], "MLB")

    def test_a_retired_player_keeps_his_last_club_without_a_roster_level(self):
        values = bio_values(
            major_leaguer(active=False, id=120074, fullName="David Ortiz"),
            sport_id=None,
        )
        self.assertEqual(values["mlb_org"], "NYY")
        self.assertNotIn("roster_status", values)
        self.assertFalse(values["active"])

    def test_a_failed_mlb_list_does_not_mark_everyone_as_minors(self):
        values = bio_values(
            minor_leaguer(),
            sport_id=11,
            teams_by_id={512: {"parentOrgId": 116}},
            mlb_list_ok=False,
        )
        self.assertEqual(values["mlb_org"], "DET")
        self.assertNotIn("roster_status", values)

    def test_the_higher_level_wins_when_a_player_is_on_two_lists(self):
        listed = merge_people(
            [
                (11, [{"id": 5, "fullName": "Minors First"}, {"id": 6, "fullName": "Only Minors"}]),
                (1, [{"id": 5, "fullName": "Majors"}]),
            ]
        )
        self.assertEqual(listed["5"], ({"id": 5, "fullName": "Majors"}, 1))
        self.assertEqual(listed["6"][1], 11)

        again = merge_people(
            [
                (1, [{"id": 5, "fullName": "Majors"}]),
                (11, [{"id": 5, "fullName": "Minors Later"}]),
            ]
        )
        self.assertEqual(again["5"][0]["fullName"], "Majors")


class SyncBiosTests(TestCase):
    def test_existing_player_is_updated_and_a_missing_mlbid_is_created(self):
        club = Team.objects.create(full_name="Test Club", abbreviation="TST")
        stored = Player.objects.create(
            mlb_id="592450",
            name="Old Name",
            first_name="Old",
            last_name="Name",
            team=club,
            position="SS",
            stats={"2025_majors_hit": {"hr": 9}},
            options=1,
            roster_40man=True,
        )
        Player.objects.filter(pk=stored.mlb_id).update(simple_position="SS", player_level="MLB", options=1)

        def fetch_people(mlb_ids):
            raise AssertionError(mlb_ids)

        counts = sync_bios(
            {
                "592450": (major_leaguer(), 1),
                "800001": (minor_leaguer(), 11),
            },
            {512: {"id": 512, "parentOrgId": 116}},
            fetch_people,
        )
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["created"], 1)

        stored.refresh_from_db()
        self.assertEqual(stored.name, "Aaron Judge")
        self.assertEqual(stored.height, "6' 7\"")
        self.assertEqual(stored.weight, "282")
        self.assertEqual(stored.position, "RF")
        self.assertEqual(stored.simple_position, "OF")
        self.assertEqual(stored.mlb_org, "NYY")
        self.assertEqual(stored.roster_status, "MLB")
        self.assertEqual(stored.birthdate, datetime.date(1992, 4, 26))
        self.assertEqual(stored.team_id, club.id)
        self.assertEqual(stored.stats, {"2025_majors_hit": {"hr": 9}})
        self.assertEqual(stored.options, 1)
        self.assertTrue(stored.roster_40man)
        self.assertEqual(stored.player_level, "MLB")

        created = Player.objects.get(mlb_id="800001")
        self.assertEqual(created.name, "Kid Player")
        self.assertEqual(created.mlb_org, "DET")
        self.assertEqual(created.roster_status, "MINORS")
        self.assertEqual(created.position, "P")
        self.assertEqual(created.simple_position, "P")
        self.assertIsNone(created.team_id)
        self.assertFalse(created.is_owned)
        self.assertFalse(created.has_appeared_in_majors)

        again = sync_bios(
            {
                "592450": (major_leaguer(), 1),
                "800001": (minor_leaguer(), 11),
            },
            {512: {"id": 512, "parentOrgId": 116}},
            fetch_people,
        )
        self.assertEqual(again["updated"], 0)
        self.assertEqual(again["unchanged"], 2)
        self.assertEqual(again["created"], 0)

    def test_a_stored_player_missing_from_the_lists_is_read_by_mlbid(self):
        Player.objects.create(mlb_id="120074", name="David Ortiz", first_name="David", last_name="Ortiz")
        Player.objects.filter(pk="120074").update(roster_status="MINORS", height="6' 3\"")

        def fetch_people(mlb_ids):
            self.assertEqual(mlb_ids, ["120074"])
            person = major_leaguer(
                id=120074,
                fullName="David Ortiz",
                useName="David",
                useLastName="Ortiz",
                active=False,
                height="6' 3\"",
                weight=230,
                primaryPosition={"abbreviation": "DH"},
            )
            return {120074: person}, set()

        counts = sync_bios({}, {}, fetch_people, create=True)
        self.assertEqual(counts["updated"], 1)
        player = Player.objects.get(mlb_id="120074")
        self.assertEqual(player.weight, "230")
        self.assertEqual(player.position, "DH")
        self.assertEqual(player.simple_position, "DH")
        self.assertEqual(player.mlb_org, "NYY")
        self.assertEqual(player.roster_status, "MINORS")
        self.assertFalse(player.active)

    def test_an_id_mlb_does_not_have_is_left_alone(self):
        Player.objects.create(mlb_id="999001", name="Gone Player", height="5' 10\"")

        counts = sync_bios({}, {}, lambda ids: ({}, {"999001"}))
        self.assertEqual(counts["not_found"], 1)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(Player.objects.get(mlb_id="999001").height, "5' 10\"")

    def test_dry_run_writes_nothing(self):
        Player.objects.create(mlb_id="592450", name="Old Name")
        counts = sync_bios(
            {"592450": (major_leaguer(), 1), "800001": (minor_leaguer(), 11)},
            {512: {"parentOrgId": 116}},
            lambda ids: (_ for _ in ()).throw(AssertionError(ids)),
            dry_run=True,
        )
        self.assertEqual(counts["updated"], 1)
        self.assertEqual(counts["created"], 1)
        self.assertEqual(Player.objects.get(mlb_id="592450").name, "Old Name")
        self.assertFalse(Player.objects.filter(mlb_id="800001").exists())

    def test_existing_only_does_not_insert(self):
        counts = sync_bios(
            {"800001": (minor_leaguer(), 11)},
            {512: {"parentOrgId": 116}},
            lambda ids: ({}, set()),
            create=False,
        )
        self.assertEqual(counts["created"], 0)
        self.assertFalse(Player.objects.filter(mlb_id="800001").exists())

    def test_one_players_update_does_not_wipe_another_players_fields(self):
        Player.objects.create(mlb_id="1", name="Keep Weight", weight="180", height="5' 8\"", position="P")
        Player.objects.create(mlb_id="2", name="Keep Height", weight="200", height="6' 2\"", position="C")
        Player.objects.filter(pk="1").update(simple_position="P", weight="180")
        Player.objects.filter(pk="2").update(simple_position="C", height="6' 2\"")

        listed = {
            "1": (major_leaguer(id=1, useName="Keep", useLastName="Weight", weight=180, height="6' 0\"", primaryPosition={"abbreviation": "P"}), 1),
            "2": (major_leaguer(id=2, useName="Keep", useLastName="Height", weight=210, height="6' 2\"", primaryPosition={"abbreviation": "C"}, currentTeam={"id": 119}), 1),
        }
        counts = sync_bios(listed, {}, lambda ids: ({}, set()))
        self.assertEqual(counts["updated"], 2)
        first = Player.objects.get(mlb_id="1")
        second = Player.objects.get(mlb_id="2")
        self.assertEqual(first.height, "6' 0\"")
        self.assertEqual(first.weight, "180")
        self.assertEqual(second.height, "6' 2\"")
        self.assertEqual(second.weight, "210")
        self.assertEqual(second.mlb_org, "LAD")
        self.assertEqual(first.simple_position, "P")
        self.assertEqual(second.simple_position, "C")

    def test_a_blank_simple_position_is_filled_without_a_full_save(self):
        Player.objects.create(mlb_id="592450", name="Aaron Judge", position=None)
        Player.objects.filter(pk="592450").update(simple_position=None, options=2)
        sync_bios({"592450": (major_leaguer(primaryPosition={"abbreviation": "CF"}), 1)}, {}, lambda ids: ({}, set()))
        player = Player.objects.get(mlb_id="592450")
        self.assertEqual(player.position, "CF")
        self.assertEqual(player.simple_position, "OF")
        self.assertEqual(player.options, 2)

    def test_a_short_run_does_not_reread_players_left_off_the_cap(self):
        Player.objects.create(mlb_id="1", name="On List", roster_status="MLB", height="6' 7\"")
        Player.objects.create(mlb_id="2", name="Also Listed", roster_status="MLB", height="6' 2\"")
        Player.objects.filter(pk__in=["1", "2"]).update(simple_position="P")
        asked = []

        def fetch_people(mlb_ids):
            asked.extend(mlb_ids)
            return {}, set()

        first = major_leaguer(
            id=1,
            useName="On",
            useLastName="List",
            height="6' 7\"",
            primaryPosition={"abbreviation": "P"},
        )
        second = major_leaguer(
            id=2,
            useName="Also",
            useLastName="Listed",
            height="6' 2\"",
            weight=210,
            primaryPosition={"abbreviation": "P"},
        )
        counts = sync_bios({"1": (first, 1), "2": (second, 1)}, {}, fetch_people, limit=1)
        self.assertEqual(asked, [])
        self.assertEqual(counts["updated"] + counts["unchanged"], 1)
        self.assertEqual(Player.objects.get(mlb_id="2").height, "6' 2\"")

    def test_an_unchanged_position_keeps_a_specific_simple_position(self):
        Player.objects.create(mlb_id="592450", name="Aaron Judge", position="SS", height="6' 0\"")
        Player.objects.filter(pk="592450").update(simple_position="SS", options=2)
        person = major_leaguer(primaryPosition={"abbreviation": "SS"}, height="6' 7\"")
        sync_bios({"592450": (person, 1)}, {}, lambda ids: ({}, set()))
        player = Player.objects.get(mlb_id="592450")
        self.assertEqual(player.position, "SS")
        self.assertEqual(player.simple_position, "SS")
        self.assertEqual(player.height, "6' 7\"")
        self.assertEqual(player.options, 2)


class CommandTests(TestCase):
    @patch("npl.management.commands.sync_mlb_players.fetch_teams", return_value=[])
    @patch("npl.management.commands.sync_mlb_players.Command.fetch_people")
    @patch("npl.management.commands.sync_mlb_players.Command.fetch_season_players")
    def test_the_command_updates_and_imports(self, fetch_season, fetch_people, _teams):
        Player.objects.create(mlb_id="592450", name="Old Name", team=None)
        fetch_season.return_value = (
            [
                (1, [major_leaguer()]),
                (11, [minor_leaguer()]),
            ],
            ["A- (404)"],
        )
        fetch_people.return_value = ({}, set())

        call_command("sync_mlb_players", "--mlb-ids", "592450,800001")

        judge = Player.objects.get(mlb_id="592450")
        self.assertEqual(judge.height, "6' 7\"")
        self.assertEqual(judge.mlb_org, "NYY")
        kid = Player.objects.get(mlb_id="800001")
        self.assertEqual(kid.name, "Kid Player")
        self.assertEqual(kid.roster_status, "MINORS")
        fetch_people.assert_called()
