import time

import pytest

from skillradar.clean.redact import redact


def clean(text):
    return redact(text).text


class TestEmails:
    def test_plain_and_markdown_mail_links(self):
        text = "an [laura.zaiss@aragon-gmbh.com](mailto:laura.zaiss@aragon-gmbh.com) senden"
        assert clean(text) == "an [[email]](mailto:[email]) senden"

    def test_count(self):
        assert redact("a@b.de und c.d@e-f.com").emails == 2


class TestLinks:
    @pytest.mark.parametrize("link", ["https://karriere.firma.de/job?id=1", "www.firma.de/jobs"])
    def test_links(self, link):
        assert clean(f"Mehr unter {link} lesen") == "Mehr unter [link] lesen"

    def test_tech_names_with_dots_stay(self):
        assert clean("Node.js, ASP.NET und Vue.js") == "Node.js, ASP.NET und Vue.js"


class TestPhones:
    @pytest.mark.parametrize(
        "phone",
        [
            "+49 (0) 30 408 06 - 35 10",
            "0711/17-99000",
            "0351-458-6060",
            "0721 35450-380",
            "(0711) 123 456",
            "+49 6196 996 10005",
            "0049 89 1234567",
        ],
    )
    def test_formats(self, phone):
        assert clean(f"Tel: {phone}.") == "Tel: [phone]."

    @pytest.mark.parametrize(
        "text",
        [
            "01067 Dresden",
            "Projekte von 2020 - 2024",
            "Version 3.0 2023",
            "50.000 - 60.000 € im Jahr",
            "0 - 3 Jahre Erfahrung",
            "Kennziffer VA35-86632-DD",
        ],
    )
    def test_numbers_that_are_not_phones(self, text):
        assert clean(text) == text

    def test_does_not_join_lines(self):
        assert clean("Tel. 0711 12281069\n2026 Start") == "Tel. [phone]\n2026 Start"


class TestNames:
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("bei Frau Madeleine Oehme.", "bei Frau [name]."),
            (
                "Frau Prof. Dr. Sandra M Blois // Frau Ramia Müllermeister",
                "Frau [name] // Frau [name]",
            ),
            ("von Herrn Prof. Dr. Ingo Röder unter", "von Herrn [name] unter"),
            ("an Frau Kalinowski (-1192)", "an Frau [name] (-1192)"),
            (
                "Diese beantwortet Ihnen gerne Herr Denis Li.",
                "Diese beantwortet Ihnen gerne Herr [name].",
            ),
        ],
    )
    def test_salutation(self, text, expected):
        assert clean(text) == expected

    def test_name_does_not_take_the_next_line(self):
        text = "bei Frau Madeleine Oehme.\n\nBewerbungsformular"
        assert clean(text) == "bei Frau [name].\n\nBewerbungsformular"

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("Ansprechpartnerin:**\nLisa Schuppeli", "Ansprechpartnerin:**\n[name]"),
            (
                "Ansprechpartner*in ist Romina Esser. Du hast",
                "Ansprechpartner*in ist [name]. Du hast",
            ),
            ("Ihr Ansprechpartner: Mathias Timm", "Ihr Ansprechpartner: [name]"),
        ],
    )
    def test_after_contact_word(self, text, expected):
        assert clean(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "Du bist Ansprechpartner:in für unsere Teams",
            "Als Ansprechpartner für Kunden",
            "Ansprechpartner\n\nMöchtest Du Teil unseres Teams werden?",
        ],
    )
    def test_contact_word_in_normal_sentences(self, text):
        assert clean(text) == text

    def test_name_line_next_to_phone(self):
        text = "Kontakt:\n\nChristine Höpfner\n+49 (0) 30 408 06 - 35 10"
        assert clean(text) == "Kontakt:\n\n[name]\n[phone]"

    def test_name_line_without_contact_data_stays(self):
        text = "Was wir nutzen\n\nApache Kafka\nviel Python"
        assert clean(text) == text

    def test_count(self):
        result = redact("Frau Anna Weber und Ansprechpartner: Tom Berg")
        assert result.names == 2


class TestSkillsAreKept:
    def test_typical_requirements(self):
        text = (
            "Dein Profil:\n- Erfahrung mit Python, SQL, Spark und Apache Kafka\n"
            "- Kenntnisse in dbt, Apache Airflow, Azure und Docker\n- Deutsch C1"
        )
        assert clean(text) == text

    def test_full_posting(self):
        text = (
            "Wir suchen einen Data Engineer (m/w/d).\n"
            "Deine Aufgaben: Pipelines mit Databricks und Kafka bauen.\n"
            "Fragen? Ansprechpartnerin: Frau Dr. Eva Klein, Tel. 0711 123456, eva.klein@firma.de"
        )
        result = redact(text)
        assert "Databricks und Kafka" in result.text
        assert "Eva" not in result.text and "Klein" not in result.text
        assert (result.emails, result.phones, result.names) == (1, 1, 1)


def test_empty_text():
    assert redact("") == redact("")
    assert clean("") == ""


def test_long_hostile_input_is_fast():
    # Guards against regexes that take very long on some inputs.
    text = ("Frau " + "Aa " * 2000 + "0" + " 1" * 5000 + "a@" * 2000) * 5
    start = time.perf_counter()
    redact(text)
    assert time.perf_counter() - start < 2


def test_salutation_after_contact_word_is_counted_once():
    result = redact("Ansprechpartnerin: Frau Dr. Eva Klein")
    assert result.text == "Ansprechpartnerin: Frau [name]"
    assert result.names == 1


class TestCasesFoundInRealData:
    def test_plural_contact_word_in_duties(self):
        text = "mit internen und externen Ansprechpartnern\n  *  Umgang mit sensiblen Daten"
        assert clean(text) == text

    def test_single_word_after_contact_word_stays(self):
        text = "Persönlichen Ansprechpartner\n\n\nUns findest Du unter: [link]"
        assert clean(text) == text

    @pytest.mark.parametrize("name", ["René Quack", "Zlatan Toromanović", "Zoë Ünal"])
    def test_accented_names(self, name):
        assert clean(f"Diese beantwortet Ihnen gerne Herr {name}.") == (
            "Diese beantwortet Ihnen gerne Herr [name]."
        )

    def test_name_two_lines_above_phone(self):
        text = "Julia Rummel\nRecruiting Managerin\nTel: 0711 123456"
        assert clean(text) == "[name]\nRecruiting Managerin\nTel: [phone]"

    def test_bold_name_line(self):
        assert clean("**Anika Kailer**\nanika@firma.de") == "[name]\n[email]"

    @pytest.mark.parametrize("heading", ["Unsere Leistungen", "Ihre Bewerbung", "Recruiting Team"])
    def test_headings_near_contact_data_stay(self, heading):
        text = f"{heading}\n\nTel: 0711 123456"
        assert clean(text) == f"{heading}\n\nTel: [phone]"


def test_contact_word_does_not_reach_over_blank_lines():
    text = "Persönlichen Ansprechpartner\n\n\nMehr Stellen findest Du unter [link]"
    assert clean(text) == text


@pytest.mark.parametrize("title", ["Data Engineer", "Software Entwickler", "Product Manager"])
def test_job_title_line_near_contact_data_stays(title):
    text = f"{title}\n(m/w/d)\n\nbewerbung@firma.de"
    assert clean(text) == f"{title}\n(m/w/d)\n\n[email]"
