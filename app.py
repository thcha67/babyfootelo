from dash import Dash, html, dcc, Input, Output, State, dash_table, set_props, no_update
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import pytz
import plotly.graph_objects as go
from datetime import datetime

# Configurer l'accès à Google Sheets
TEST = False
SHEET_URL = "https://docs.google.com/spreadsheets/d/1ZAHNcvfIhZX6mg0v8THsSA71gsSceSbN2CfQtcYjBrM/edit?gid=0#gid=0" if not TEST else "https://docs.google.com/spreadsheets/d/1YGxgv7Q-GdLtDkUv881KeUKRCSxS4vLXv1swncRtt4M/edit"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = "credentials.json"

TZ = pytz.timezone("America/Toronto")


def get_google_sheet(sheet_name):
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet(sheet_name)

def get_data(sheet_name):
    sheet = get_google_sheet(sheet_name=sheet_name)
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def update_google_sheet(data, sheet_name):
    sheet = get_google_sheet(sheet_name=sheet_name)
    sheet.clear()
    sheet.update([data.columns.values.tolist()] + data.values.tolist())

def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def calculate_elo(winner, loser, score_w, score_l):
    df = get_data("players")

    winner_row = df[df['player_name'] == winner].index[0]
    loser_row = df[df['player_name'] == loser].index[0]
    
    winner_elo = df.at[winner_row, 'elo']
    loser_elo = df.at[loser_row, 'elo']
    
    expected_w = expected_score(winner_elo, loser_elo)
    expected_l = expected_score(loser_elo, winner_elo)
    
    margin_multiplier = max((score_w - score_l) / 10, 1)

    # Update ELO scores
    df.at[winner_row, 'elo'] = winner_elo + round(32 * margin_multiplier * (1 - expected_w)) # k factor of 32
    df.at[loser_row, 'elo'] = loser_elo + round(32 * margin_multiplier * (0 - expected_l))
    
    # Update number of games played
    df.at[winner_row, 'n_games_played'] += 1
    df.at[loser_row, 'n_games_played'] += 1

    # update win streak
    df.at[winner_row, "win_streak"] += 1
    df.at[loser_row, "win_streak"] = 0

    # Update record
    winner_n_wins, winner_n_losses = df.at[winner_row, "record"].split("-")
    loser_n_wins, loser_n_losses = df.at[loser_row, "record"].split("-")

    df.at[winner_row, "record"] = f"{int(winner_n_wins) + 1}-{winner_n_losses}"
    df.at[loser_row, "record"] = f"{loser_n_wins}-{int(loser_n_losses) + 1}"
    
    return df


def record_match(winner, loser, score_w, score_l, elo_w, elo_l):
    df = get_data("match_history")

    # Générer l'ID du match (date du match)
    match_id = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")

    # Ajoute une nouvelle ligne à la feuille match_history
    match_data = [match_id, winner, loser, score_w, score_l, elo_w, elo_l]
    # append match data to df
    if len(df) == 0:
        df = pd.DataFrame([match_data], columns=["id", "winner", "loser", "score_w", "score_l", "elo_w", "elo_l"])
    else:
        df.loc[len(df)] = match_data

    return df


def create_table(df):
    table = df.sort_values(by='elo', ascending=False).to_dict('records')
    table_style = [ # Highlight top 3 players
        {"if": {"filter_query": f'{{player_name}} eq "{table[i]["player_name"]}"', "column_id": "player_name"}, "backgroundColor": c}
        for i, c in zip([0, 1, 2], ["#FFD700", "#C0C0C0", "#cd7f32"])
        ]
    return table, table_style

def show_alert(message, color="danger"):
    set_props("alert", dict(is_open=True, children=message, color=color))
    return no_update

app = Dash("ELO babyfoot GPH", external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = "ELO babyfoot GPH"

server = app.server

app.layout = dbc.Container([
    dbc.Alert(id="alert", is_open=False, duration=2000, color="danger", style={"position": "absolute", "top": "0px", "z-index": 9999, "width": "98vw"}),
    html.H1("ELO babyfoot GPH", style={"textAlign": "center", "margin-bottom": "10px"}),
    dbc.Row([
        dbc.Col([
            html.Label("Joueur 1"),
            dcc.Dropdown(id='player1-dropdown', options=[]),
            html.Label("Joueur 2"),
            dcc.Dropdown(id='player2-dropdown', options=[]),
        ], width=4),
        dbc.Col([
            html.Label("Score 1"),
            dbc.Input(id='score-input-player1', type='number', placeholder="Score du joueur 1", min=0, max=10, inputmode="numeric", maxlength=2),
            html.Label("Score 2"),
            dbc.Input(id='score-input-player2', type='number', placeholder="Score du joueur 2", min=0, max=10, inputmode="numeric", maxlength=2),
            dbc.Button("Confirmer", id='confirm-btn', n_clicks=0),
        ], width=4),
        dbc.Col([
            html.Label("Ajouter un joueur (max. 15 caractères)"),
            dbc.Input(id='new-player-name', type='text', placeholder="Nom du joueur", maxlength=15),
            dbc.Button("Ajouter le joueur", id='add-player-btn', n_clicks=0),
        ], width=4)
    ]),
    dbc.Row([
        dash_table.DataTable(
            id='players-table', 
            columns=[{"name": col, "id": col} for col in ["player_name", "elo", "n_games_played", "record", "win_streak"]], 
            data=[], style_table={"margin-top": "50px", "overflowY": "auto", "height": "55vh"}, 
            sort_action="native", sort_mode="single", fixed_rows={'headers': True},
            style_header={'backgroundColor': 'var(--bs-blue)', 'color': 'white', 'fontWeight': 'bold'},
            style_cell={'width': '20%','textOverflow': 'ellipsis','overflow': 'hidden', 'textAlign': 'center'},
        ),
    ]),
    dbc.Modal([
        dbc.ModalHeader("Statistiques du joueur"),
        dbc.ModalBody(id="player-stats-content"),
    ], id="player-stats", size="lg"),
], fluid=True)

@app.callback(
    Output('players-table', 'data'),
    Output('players-table', 'style_data_conditional'),
    Input('players-table', 'id')
)
def update_table_on_load(_):
    return create_table(get_data("players"))

@app.callback(
    Output('player1-dropdown', 'options'),
    Output('player2-dropdown', 'options'),
    Input('players-table', 'data'),
)
def update_dropdowns(data):
    player_names = [player["player_name"] for player in data]
    return player_names, player_names

@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Output("players-table", "style_data_conditional", allow_duplicate=True),
    Output("player1-dropdown", "value"),
    Output("player2-dropdown", "value"),
    Output("score-input-player1", "value"),
    Output("score-input-player2", "value"),
    Input('confirm-btn', 'n_clicks'),
    State('player1-dropdown', 'value'),
    State('player2-dropdown', 'value'),
    State('score-input-player1', 'value'),
    State('score-input-player2', 'value'),
    prevent_initial_call=True
)
def update_scores(_, player1, player2, score1, score2):
    if not player1 or not player2:
        show_alert("Veuillez sélectionner deux joueurs.")
    elif player1 == player2:
        show_alert("Veuillez sélectionner deux joueurs différents.")
    elif score1 is None or score2 is None:
        show_alert("Veuillez entrer les scores.")
    elif max(score1, score2) != 10 or min(score1, score2) < 0:
        show_alert("Les scores doivent être compris entre 0 et 10.")
    else:
        if score1 == 10: # player1 wins
            players = calculate_elo(player1, player2, score1, score2)
            winner, loser, score_w, score_l = player1, player2, score1, score2
        else: 
            players = calculate_elo(player2, player1, score2, score1)
            winner, loser, score_w, score_l = player2, player1, score2, score1

        new_elo_winner = players[players["player_name"] == winner]["elo"].values[0]
        new_elo_loser = players[players["player_name"] == loser]["elo"].values[0]

        match_history = record_match(winner, loser, score_w, score_l, new_elo_winner, new_elo_loser)

        update_google_sheet(players, "players")
        update_google_sheet(match_history, "match_history")
        
        show_alert(f"Les scores ont été mis à jour.", color="success")
        return *create_table(players), None, None, None, None
    return no_update, no_update, no_update, no_update, no_update, no_update # cannot raise PreventUpdate to still show alert

@app.callback(
    Output("player-stats", "is_open"),
    Output("player-stats-content", "children"),
    Input("players-table", "active_cell"),
    State("players-table", "data"),
)
def show_player_stats(active_cell, data):
    if not active_cell:
        raise PreventUpdate
    
    player_name = data[active_cell["row"]]["player_name"]
    
    match_history = get_data("match_history")
    
    if match_history.empty:
        return True, "Aucun match enregistré."
    
    games_won = match_history[match_history["winner"] == player_name]
    games_lost = match_history[match_history["loser"] == player_name]

    dates = games_won["id"].tolist() + games_lost["id"].tolist()
    elo = games_won["elo_w"].tolist() + games_lost["elo_l"].tolist()
    opponents = games_won["loser"].tolist() + games_lost["winner"].tolist()
    win_or_loss = ["Victoire"] * len(games_won) + ["Défaite"] * len(games_lost)
    scores = games_won["score_l"].tolist() + games_lost["score_l"].tolist()

    dates, elo, opponents, win_or_loss, scores = zip(*sorted(zip(dates, elo, opponents, win_or_loss, scores), key=lambda x: x[0]))

    hovertext = [f"{w_l} contre {opponent} (10-{score})" for score, w_l, opponent in zip(scores, win_or_loss, opponents)]

    figure = go.Figure()
    figure.add_trace(go.Scatter(x=dates, y=elo, mode='lines+markers', name='ELO', line=dict(color='blue'), hovertext=hovertext))
    figure.update_layout(title=f"Évolution de l'ELO de {player_name}", xaxis_title="Date", yaxis_title="ELO", template="plotly_white")

    return True, dcc.Graph(figure=figure)


@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Output("players-table", "style_data_conditional", allow_duplicate=True),
    Output("new-player-name", "value"),
    Input('add-player-btn', 'n_clicks'),
    State('new-player-name', 'value'),
    prevent_initial_call=True
)
def add_player(_, new_player_name):
    if not new_player_name:
        show_alert("Veuillez entrer un nom de joueur.")
        return no_update, no_update, no_update
    
    players = get_data("players")

    if new_player_name in players['player_name'].values:
        show_alert("Ce joueur existe déjà.")
        return no_update, no_update, no_update

    new_player = pd.DataFrame([[new_player_name, 800, 0, "0-0", "0"]], columns=['player_name', 'elo', 'n_games_played', "record", "win_streak"])
    players = pd.concat([players, new_player], ignore_index=True)

    update_google_sheet(players, "players")
    show_alert(f"Le joueur {new_player_name} a été ajouté.", color="success")
    return *create_table(players), None


if __name__ == '__main__':
    app.run(debug=TEST)
