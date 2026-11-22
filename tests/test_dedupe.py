from job_collector.dedupe import company_key, dedupe, title_key
from job_collector.models import Job


def job(source: str, url: str, company: str, title: str) -> Job:
    return Job(source, url, title, company, "Tel Aviv", url)


def test_company_and_title_keys() -> None:
    assert company_key("Check Point Software Technologies Ltd.") == "check point"
    assert company_key("Check Point") == "check point"
    assert title_key("QA Engineer & Production Support 198801") == "qa engineer production support"


def test_same_url_is_dropped() -> None:
    a = job("LinkedIn", "https://l/1", "Acme", "NOC Engineer")
    b = job("LinkedIn", "https://l/1", "Acme", "NOC Engineer")
    assert dedupe([a, b]) == [a]


def test_company_site_wins_over_linkedin() -> None:
    linkedin = job("LinkedIn", "https://l/1", "Cato Networks", "DevOps Engineer")
    greenhouse = job("Greenhouse", "https://g/1", "Cato Networks", "DevOps Engineer ")
    [kept] = dedupe([linkedin, greenhouse])
    assert kept is greenhouse
    assert kept.also_in == ["LinkedIn"]


def test_hidden_companies_are_not_merged() -> None:
    a = job("LinkedIn", "https://l/1", "(hidden)", "Technician")
    b = job("LinkedIn", "https://l/2", "(hidden)", "Technician")
    assert len(dedupe([a, b])) == 2


def test_different_titles_are_kept() -> None:
    a = job("LinkedIn", "https://l/1", "KLA", "Final Integration Engineer")
    b = job("LinkedIn", "https://l/2", "KLA", "NPI Integration Engineer")
    assert len(dedupe([a, b])) == 2
