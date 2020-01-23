from unittest.mock import MagicMock

import pytest

from prefect.agent import Agent
from prefect.engine.state import Scheduled
from prefect.utilities.configuration import set_temporary_config
from prefect.utilities.exceptions import AuthorizationError
from prefect.utilities.graphql import GraphQLResult


def test_agent_init(runner_token):
    agent = Agent()
    assert agent


def test_multiple_agent_init_doesnt_duplicate_logs(runner_token):
    a, b, c = Agent(), Agent(), Agent()
    assert len(c.logger.handlers) == 1


def test_agent_config_options(runner_token):
    with set_temporary_config({"cloud.agent.auth_token": "TEST_TOKEN"}):
        agent = Agent()
        assert agent.labels == []
        assert agent.env_vars == dict()
        assert agent.client.get_auth_token() == "TEST_TOKEN"
        assert agent.name == "agent"
        assert agent.logger
        assert agent.logger.name == "agent"


def test_agent_name_set_options(monkeypatch, runner_token):
    # Default
    agent = Agent()
    assert agent.name == "agent"
    assert agent.logger.name == "agent"

    # Init arg
    agent = Agent(name="test1")
    assert agent.name == "test1"
    assert agent.logger.name == "test1"

    # Config
    with set_temporary_config({"cloud.agent.name": "test2"}):
        agent = Agent()
        assert agent.name == "test2"
        assert agent.logger.name == "test2"


def test_agent_log_level(runner_token):
    with set_temporary_config({"cloud.agent.auth_token": "TEST_TOKEN"}):
        agent = Agent()
        assert agent.logger.level == 20


def test_agent_log_level_responds_to_config(runner_token):
    with set_temporary_config(
        {"cloud.agent.auth_token": "TEST_TOKEN", "cloud.agent.level": "DEBUG"}
    ):
        agent = Agent()
        assert agent.logger.level == 10


def test_agent_env_vars(runner_token):
    with set_temporary_config({"cloud.agent.auth_token": "TEST_TOKEN"}):
        agent = Agent(env_vars=dict(AUTH_THING="foo"))
        assert agent.env_vars == dict(AUTH_THING="foo")


def test_agent_labels(runner_token):
    with set_temporary_config({"cloud.agent.auth_token": "TEST_TOKEN"}):
        agent = Agent(labels=["test", "2"])
        assert agent.labels == ["test", "2"]


def test_agent_labels_from_config_var(runner_token):
    with set_temporary_config({"cloud.agent.labels": "['test', '2']"}):
        agent = Agent()
        assert agent.labels == ["test", "2"]


def test_agent_log_level_debug(runner_token):
    with set_temporary_config(
        {"cloud.agent.auth_token": "TEST_TOKEN", "cloud.agent.level": "DEBUG"}
    ):
        agent = Agent()
        assert agent.logger.level == 10


def test_agent_fails_no_auth_token():
    with pytest.raises(AuthorizationError):
        agent = Agent()
        agent.query_tenant_id()


def test_agent_fails_no_runner_token(monkeypatch):
    post = MagicMock(
        return_value=MagicMock(
            json=MagicMock(
                return_value=dict(data=dict(authInfo=MagicMock(apiTokenScope="USER")))
            )
        )
    )
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    with pytest.raises(AuthorizationError):
        agent = Agent()
        agent.query_tenant_id()


def test_query_tenant_id(monkeypatch, runner_token):
    post = MagicMock(
        return_value=MagicMock(
            json=MagicMock(return_value=dict(data=dict(tenant=[dict(id="id")])))
        )
    )
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    agent = Agent()
    tenant_id = agent.query_tenant_id()
    assert tenant_id == "id"


def test_query_tenant_id_not_found(monkeypatch, runner_token):
    post = MagicMock(
        return_value=MagicMock(json=MagicMock(return_value=dict(data=dict(tenant=[]))))
    )
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    agent = Agent()
    tenant_id = agent.query_tenant_id()
    assert not tenant_id


def test_query_flow_runs(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(
                getRunsInQueue=MagicMock(flow_run_ids=["id"]), flow_run=[{"id": "id"}]
            )
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    agent = Agent()
    flow_runs = agent.query_flow_runs(tenant_id="id")
    assert flow_runs == [{"id": "id"}]


def test_query_flow_runs_ignores_currently_submitting_runs(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(
                getRunsInQueue=MagicMock(flow_run_ids=["id1", "id2"]),
                flow_run=[{"id1": "id1"}],
            )
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    agent = Agent()
    agent.submitting_flow_runs.add("id2")
    agent.query_flow_runs(tenant_id="id")

    assert len(gql_return.call_args_list) == 2
    assert (
        'id: { _in: ["id1"] }'
        in list(gql_return.call_args_list[1][0][0]["query"].keys())[0]
    )


def test_update_states_passes_no_task_runs(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(set_flow_run_state=None, set_task_run_state=None)
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    agent = Agent()
    assert not agent.update_state(
        flow_run=GraphQLResult(
            {
                "id": "id",
                "serialized_state": Scheduled().serialize(),
                "version": 1,
                "task_runs": [],
            }
        ),
        deployment_info="test",
    )


def test_update_states_passes_task_runs(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(set_flow_run_state=None, set_task_run_state=None)
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    agent = Agent()
    assert not agent.update_state(
        flow_run=GraphQLResult(
            {
                "id": "id",
                "serialized_state": Scheduled().serialize(),
                "version": 1,
                "task_runs": [
                    GraphQLResult(
                        {
                            "id": "id",
                            "version": 1,
                            "serialized_state": Scheduled().serialize(),
                        }
                    )
                ],
            }
        ),
        deployment_info="test",
    )


def test_mark_failed(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(set_flow_run_state=None, set_task_run_state=None)
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    agent = Agent()
    assert not agent.mark_failed(
        flow_run=GraphQLResult(
            {
                "id": "id",
                "serialized_state": Scheduled().serialize(),
                "version": 1,
                "task_runs": [],
            }
        ),
        exc=Exception(),
    )


def test_deploy_flows_passes_base_agent(runner_token):
    agent = Agent()
    with pytest.raises(NotImplementedError):
        agent.deploy_flow(None)


def test_heartbeat_passes_base_agent(runner_token):
    agent = Agent()
    assert not agent.heartbeat()


def test_agent_connect(monkeypatch, runner_token):
    post = MagicMock(
        return_value=MagicMock(
            json=MagicMock(return_value=dict(data=dict(tenant=[dict(id="id")])))
        )
    )
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    agent = Agent()
    assert agent.agent_connect() == "id"


def test_agent_connect_no_tenant_id(monkeypatch, runner_token):
    post = MagicMock(
        return_value=MagicMock(
            json=MagicMock(return_value=dict(data=dict(tenant=[dict(id=None)])))
        )
    )
    session = MagicMock()
    session.return_value.post = post
    monkeypatch.setattr("requests.Session", session)

    agent = Agent()
    with pytest.raises(ConnectionError):
        assert agent.agent_connect()


def test_on_flow_run_deploy_attempt_removes_id(monkeypatch, runner_token):
    agent = Agent()
    agent.submitting_flow_runs.add("id")
    agent.on_flow_run_deploy_attempt(None, "id")
    assert len(agent.submitting_flow_runs) == 0


def test_agent_process(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(
                set_flow_run_state=None,
                set_task_run_state=None,
                getRunsInQueue=MagicMock(flow_run_ids=["id"]),
                flow_run=[
                    GraphQLResult(
                        {
                            "id": "id",
                            "serialized_state": Scheduled().serialize(),
                            "version": 1,
                            "task_runs": [
                                GraphQLResult(
                                    {
                                        "id": "id",
                                        "version": 1,
                                        "serialized_state": Scheduled().serialize(),
                                    }
                                )
                            ],
                        }
                    )
                ],
            )
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    executor = MagicMock()
    future_mock = MagicMock()
    executor.submit = MagicMock(return_value=future_mock)

    agent = Agent()
    assert agent.agent_process(executor, "id")
    assert executor.submit.called
    assert future_mock.add_done_callback.called


def test_agent_process_no_runs_found(monkeypatch, runner_token):
    gql_return = MagicMock(
        return_value=MagicMock(
            data=MagicMock(
                set_flow_run_state=None,
                set_task_run_state=None,
                getRunsInQueue=MagicMock(flow_run_ids=["id"]),
                flow_run=[],
            )
        )
    )
    client = MagicMock()
    client.return_value.graphql = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    executor = MagicMock()

    agent = Agent()
    assert not agent.agent_process(executor, "id")
    assert not executor.submit.called


def test_agent_logs_flow_run_exceptions(monkeypatch, runner_token, caplog):
    gql_return = MagicMock(
        return_value=MagicMock(data=MagicMock(writeRunLogs=MagicMock(success=True)))
    )
    client = MagicMock()
    client.return_value.write_run_logs = gql_return
    monkeypatch.setattr("prefect.agent.agent.Client", MagicMock(return_value=client))

    agent = Agent()
    agent.deploy_flow = MagicMock(side_effect=Exception("Error Here"))
    agent.deploy_and_update_flow_run(
        flow_run=GraphQLResult(
            {
                "id": "id",
                "serialized_state": Scheduled().serialize(),
                "version": 1,
                "task_runs": [
                    GraphQLResult(
                        {
                            "id": "id",
                            "version": 1,
                            "serialized_state": Scheduled().serialize(),
                        }
                    )
                ],
            }
        )
    )

    assert client.write_run_logs.called
    client.write_run_logs.assert_called_with(
        [dict(flowRunId="id", level="ERROR", message="Error Here", name="agent")]
    )
    assert "Logging platform error for flow run" in caplog.text


def test_agent_process_raises_exception_and_logs(monkeypatch, runner_token):
    client = MagicMock()
    client.return_value.graphql.side_effect = ValueError("Error")
    monkeypatch.setattr("prefect.agent.agent.Client", client)

    executor = MagicMock()

    agent = Agent()
    with pytest.raises(Exception):
        agent.agent_process(executor, "id")
        assert client.write_run_log.called
