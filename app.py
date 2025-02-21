from dash import Dash, html, dcc, Input, Output, State, dash_table, set_props, no_update
import dash_bootstrap_components as dbc
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd

# Configurer l'accès à Google Sheets
SHEET_URL = "https://docs.google.com/spreadsheets/d/1ZAHNcvfIhZX6mg0v8THsSA71gsSceSbN2CfQtcYjBrM/edit?gid=0#gid=0"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDS_FILE = "credentials.json"

def get_google_sheet():
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDS_FILE, SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_url(SHEET_URL).worksheet("players")

def get_data():
    sheet = get_google_sheet()
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def update_google_sheet(data):
    sheet = get_google_sheet()
    sheet.clear()
    sheet.update([data.columns.values.tolist()] + data.values.tolist())

# Calculer K en fonction du nombre de parties jouées
def get_k_factor(games_played):
    if games_played < 5:
        return 40
    elif games_played < 10:
        return 32
    elif games_played < 20:
        return 20
    else:
        return 15

def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

def calculate_elo(winner, loser, score_w, score_l):
    df = get_data()
    winner_row = df[df['player_name'] == winner].index[0]
    loser_row = df[df['player_name'] == loser].index[0]
    
    winner_elo = df.at[winner_row, 'elo']
    loser_elo = df.at[loser_row, 'elo']
    
    winner_games_played = df.at[winner_row, 'n_games_played']
    loser_games_played = df.at[loser_row, 'n_games_played']
    
    expected_w = expected_score(winner_elo, loser_elo)
    expected_l = expected_score(loser_elo, winner_elo)
    
    margin_multiplier = max((score_w - score_l) / 10, 1)
    
    K_w = get_k_factor(winner_games_played)
    K_l = get_k_factor(loser_games_played)
    
    df.at[winner_row, 'elo'] = winner_elo + round(K_w * margin_multiplier * (1 - expected_w))
    df.at[loser_row, 'elo'] = loser_elo + round(K_l * margin_multiplier * (0 - expected_l))
    
    df.at[winner_row, 'n_games_played'] += 1
    df.at[loser_row, 'n_games_played'] += 1
    
    update_google_sheet(df)

def create_table(df):
    return df.sort_values(by='elo', ascending=False).to_dict('records')

def show_alert(message, color="danger"):
    set_props("alert", dict(is_open=True, children=message, color=color))
    return no_update

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
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
        dash_table.DataTable(id='players-table', 
                        columns=[{"name": col, "id": col} for col in ["player_name", "elo", "n_games_played"]], 
                        data=[], style_table={"margin-top": "50px", "overflowY": "auto", "height": "55vh"}, 
                        sort_action="native", sort_mode="single", fixed_rows={'headers': True},
                        style_header={'backgroundColor': 'var(--bs-blue)', 'color': 'white', 'fontWeight': 'bold'},
                        style_cell={'width': '33%','textOverflow': 'ellipsis','overflow': 'hidden', 'textAlign': 'center'}),
    ]),
], fluid=True)

@app.callback(
    Output('players-table', 'data'),
    Input('players-table', 'id')
)
def update_table_on_load(_):
    df = get_data()
    return create_table(df)

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
        if score1 == 10:
            calculate_elo(player1, player2, score1, score2)
        else:
            calculate_elo(player2, player1, score2, score1)
        df = get_data()
        show_alert(f"Les scores ont été mis à jour.", color="success")
        return create_table(df), None, None, None, None
    
    return no_update, no_update, no_update, no_update, no_update

@app.callback(
    Output('players-table', 'data', allow_duplicate=True),
    Output("new-player-name", "value"),
    Input('add-player-btn', 'n_clicks'),
    State('new-player-name', 'value'),
    prevent_initial_call=True
)
def add_player(_, new_player_name):
    if not new_player_name:
        show_alert("Veuillez entrer un nom de joueur.")
        return no_update, no_update
    
    df = get_data()

    if new_player_name in df['player_name'].values:
        show_alert("Ce joueur existe déjà.")
        return no_update, no_update

    new_row = pd.DataFrame([[new_player_name, 800, 0]], columns=['player_name', 'elo', 'n_games_played'])
    df = pd.concat([df, new_row], ignore_index=True)
    update_google_sheet(df)
    show_alert(f"Le joueur {new_player_name} a été ajouté.", color="success")
    return create_table(df), None


server = app.server

if __name__ == '__main__':
    app.run(debug=True)
