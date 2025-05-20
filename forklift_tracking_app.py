#!/usr/bin/env python3
import dash
from dash import dcc, html
from dash.dependencies import Input, Output
import plotly.graph_objs as go
import pandas as pd
import os
import time
import glob
import math
from datetime import datetime, timedelta

# Configuration
UPDATE_INTERVAL = 1000  # Update interval in milliseconds

# Environment sizes
ENVIRONMENT_SIZE = {
    "indoor": (25, 20),  # 500 m² underground area (25m x 20m)
    "outdoor": (1000, 1000)  # 1 km² outdoor yard (1km x 1km)
}

# Charging station positions
CHARGING_STATIONS = {
    'indoor_charge1': (2, 2),
    'indoor_charge2': (23, 18),
    'outdoor_charge1': (100, 100),
    'outdoor_charge2': (900, 900)
}


# Calculate distance between two points
def calculate_distance(x1, y1, x2, y2):
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


# Get the latest data folder
def get_current_session():
    try:
        with open("current_session.txt", 'r') as f:
            folder = f.read().strip()
            if os.path.exists(folder):
                return folder
    except:
        # If file doesn't exist, find the most recent folder
        data_folders = sorted(glob.glob('forklift_data/session_*'))
        if data_folders:
            return data_folders[-1]

    return None


# Get all forklift IDs from current session
def get_forklift_ids():
    session = get_current_session()
    if not session:
        return []

    # Find all CSV files that match forklift pattern
    forklift_files = glob.glob(os.path.join(session, 'FL-*.csv'))

    # Extract forklift IDs from filenames
    forklift_ids = []
    for file in forklift_files:
        base = os.path.basename(file)
        forklift_id = base.split('_')[0]
        forklift_ids.append(forklift_id)

    return forklift_ids


# Get data for a specific forklift
def get_forklift_data(forklift_id):
    session = get_current_session()
    if not session:
        return None

    csv_path = os.path.join(session, f'{forklift_id}_data.csv')
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Handle position data based on simulator format
            if 'position.x' in df.columns and 'position.y' in df.columns:
                df['x'] = df['position.x']
                df['y'] = df['position.y']

            return df
        except Exception as e:
            print(f"Error loading forklift data: {e}")
            pass

    return None


# Get impacts data
def get_impacts_data():
    session = get_current_session()
    if not session:
        return None

    impacts_path = os.path.join(session, 'impacts.csv')
    if os.path.exists(impacts_path):
        try:
            df = pd.read_csv(impacts_path)
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            # Handle position data based on simulator format
            # The simulator stores impacts as {'position': (x, y)} in the telemetry
            if 'position.0' in df.columns and 'position.1' in df.columns:
                df['x_position'] = df['position.0']
                df['y_position'] = df['position.1']
            elif 'magnitude' in df.columns:
                # We might need to collect impacts from individual forklift data
                pass

            return df
        except Exception as e:
            print(f"Error loading impacts data: {e}")

    # If no dedicated impacts file exists, try to collect from forklift files
    try:
        impacts_df = pd.DataFrame()
        forklift_ids = get_forklift_ids()

        for forklift_id in forklift_ids:
            df = get_forklift_data(forklift_id)
            if df is not None and 'impacts' in df.columns:
                # Try to extract impact data
                forklift_impacts = pd.json_normalize(
                    df['impacts'].apply(lambda x: eval(x) if isinstance(x, str) and x else [])
                    .explode().dropna().to_list()
                )

                if not forklift_impacts.empty:
                    forklift_impacts['forklift_id'] = forklift_id
                    forklift_impacts['environment'] = df['environment'].iloc[
                        0] if 'environment' in df.columns else 'unknown'
                    impacts_df = pd.concat([impacts_df, forklift_impacts])

        if not impacts_df.empty:
            # Standardize column names
            if 'position.0' in impacts_df.columns and 'position.1' in impacts_df.columns:
                impacts_df['x_position'] = impacts_df['position.0']
                impacts_df['y_position'] = impacts_df['position.1']
            elif 'position' in impacts_df.columns:
                # Handle if position is stored as tuple string
                try:
                    impacts_df['position'] = impacts_df['position'].apply(eval)
                    impacts_df['x_position'] = impacts_df['position'].apply(
                        lambda p: p[0] if isinstance(p, tuple) else None)
                    impacts_df['y_position'] = impacts_df['position'].apply(
                        lambda p: p[1] if isinstance(p, tuple) else None)
                except:
                    pass

            return impacts_df
    except Exception as e:
        print(f"Error collecting impacts data: {e}")

    return None


# Initialize the Dash app
app = dash.Dash(__name__, update_title=None)
app.title = "Forklift Tracking System"

# Define the layout
app.layout = html.Div([
    html.H1("Forklift Tracking and Monitoring System",
            style={'textAlign': 'center', 'color': '#2c3e50', 'marginBottom': '10px'}),

    # Environment selector
    html.Div([
        html.Label("Environment:"),
        dcc.RadioItems(
            id='environment-selector',
            options=[
                {'label': 'Indoor', 'value': 'indoor'},
                {'label': 'Outdoor', 'value': 'outdoor'},
                {'label': 'All', 'value': 'all'}
            ],
            value='all',
            inline=True
        )
    ], style={'margin': '10px', 'textAlign': 'center'}),

    # Forklift selector
    html.Div([
        html.Label("Select Forklift:"),
        dcc.Dropdown(
            id='forklift-selector',
            options=[],
            value=None,
            placeholder="Select a forklift"
        )
    ], style={'margin': '10px', 'width': '50%', 'margin': 'auto'}),

    # Main display area with tabs
    dcc.Tabs([
        # Tab 1: Map View
        dcc.Tab(label='Map View', children=[
            html.Div([
                dcc.Graph(id='map-graph'),
                dcc.Interval(
                    id='map-interval',
                    interval=UPDATE_INTERVAL,
                    n_intervals=0
                )
            ])
        ]),

        # Tab 2: Statistics
        dcc.Tab(label='Statistics', children=[
            html.Div([
                html.Div([
                    html.H3("Forklift Status Summary"),
                    html.Div(id='status-summary')
                ], style={'margin': '20px'}),

                html.Div([
                    html.H3("Recent Impacts"),
                    html.Div(id='recent-impacts')
                ], style={'margin': '20px'}),

                dcc.Interval(
                    id='stats-interval',
                    interval=UPDATE_INTERVAL,
                    n_intervals=0
                )
            ])
        ]),

        # Tab 3: Battery Status
        dcc.Tab(label='Battery Status', children=[
            html.Div([
                dcc.Graph(id='battery-graph'),
                dcc.Interval(
                    id='battery-interval',
                    interval=UPDATE_INTERVAL,
                    n_intervals=0
                )
            ])
        ])
    ])
])


# Update forklift dropdown options
@app.callback(
    Output('forklift-selector', 'options'),
    [Input('map-interval', 'n_intervals')]
)
def update_forklift_options(n):
    forklift_ids = get_forklift_ids()
    return [{'label': fid, 'value': fid} for fid in forklift_ids]


# Update map
@app.callback(
    Output('map-graph', 'figure'),
    [Input('map-interval', 'n_intervals'),
     Input('environment-selector', 'value'),
     Input('forklift-selector', 'value')]
)
def update_map(n, env, selected_forklift):
    # Initialize figure
    fig = go.Figure()

    # Get all forklift IDs
    forklift_ids = get_forklift_ids()

    # Plot each forklift's position
    for forklift_id in forklift_ids:
        # Skip if not matching environment filter
        if selected_forklift and forklift_id != selected_forklift:
            continue

        df = get_forklift_data(forklift_id)
        if df is not None and not df.empty:
            # Get latest position
            latest = df.iloc[-1]
            environment = latest.get('environment', 'indoor')

            # Skip if not matching environment filter
            if env != 'all' and environment != env:
                continue

            # Get position data, handling different column naming schemes
            x = latest.get('x', latest.get('position.x', 0))
            y = latest.get('y', latest.get('position.y', 0))

            status = 'active'
            battery = latest.get('battery_level', 0)

            # Determine status based on available data
            if latest.get('standing_still', False):
                if battery < 30 and any(calculate_distance(x, y, cx, cy) < 3
                                        for name, (cx, cy) in CHARGING_STATIONS.items()
                                        if name.startswith(environment)):
                    status = 'charging'
                else:
                    status = 'idle'

            if battery <= 0:
                status = 'error'

            # Color based on status
            color = 'green'
            if status == 'charging':
                color = 'blue'
            elif status == 'maintenance':
                color = 'orange'
            elif status == 'error':
                color = 'red'
            elif status == 'idle':
                color = 'gray'
            elif battery < 20:
                color = 'yellow'

            # Add marker for forklift
            fig.add_trace(go.Scatter(
                x=[x], y=[y],
                mode='markers+text',
                marker=dict(size=15, color=color),
                text=[forklift_id],
                name=f"{forklift_id} ({status}, {battery}%)"
            ))

    # Add charging stations
    for name, (x, y) in CHARGING_STATIONS.items():
        env_type = name.split('_')[0]
        if env == 'all' or env == env_type:
            fig.add_trace(go.Scatter(
                x=[x], y=[y],
                mode='markers',
                marker=dict(
                    symbol='square',
                    size=12,
                    color='blue',
                    line=dict(width=2, color='black')
                ),
                name=f"Charging: {name}"
            ))

    # Add impacts if available
    impacts_df = get_impacts_data()
    if impacts_df is not None:
        # Filter by selected environment and last 24 hours
        if env != 'all':
            impacts_df = impacts_df[impacts_df['environment'] == env]

        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_impacts = impacts_df[impacts_df['timestamp'] > cutoff_time]

        if not recent_impacts.empty:
            # Check which position columns are available in the impacts dataframe
            pos_columns = []
            if 'x_position' in recent_impacts.columns and 'y_position' in recent_impacts.columns:
                pos_columns = ['x_position', 'y_position']
            elif 'pos_x' in recent_impacts.columns and 'pos_y' in recent_impacts.columns:
                pos_columns = ['pos_x', 'pos_y']
            elif 'x' in recent_impacts.columns and 'y' in recent_impacts.columns:
                pos_columns = ['x', 'y']

            if pos_columns:
                fig.add_trace(go.Scatter(
                    x=recent_impacts[pos_columns[0]], y=recent_impacts[pos_columns[1]],
                    mode='markers',
                    marker=dict(
                        symbol='x',
                        size=10,
                        color='red',
                        line=dict(width=1)
                    ),
                    name='Impacts (24h)'
                ))

    # Set appropriate boundaries based on environment
    if env == 'indoor':
        width, height = ENVIRONMENT_SIZE['indoor']
        title = "Indoor Forklift Tracking"
    elif env == 'outdoor':
        width, height = ENVIRONMENT_SIZE['outdoor']
        title = "Outdoor Forklift Tracking"
    else:
        # Show both environments with different scales
        width, height = ENVIRONMENT_SIZE['outdoor']
        title = "All Forklift Tracking"

    # Update layout
    fig.update_layout(
        title=title,
        xaxis=dict(range=[0, width], title="X Position (m)"),
        yaxis=dict(range=[0, height], title="Y Position (m)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
        height=600
    )

    return fig


# Update status summary
@app.callback(
    Output('status-summary', 'children'),
    [Input('stats-interval', 'n_intervals'),
     Input('environment-selector', 'value')]
)
def update_status_summary(n, env):
    forklift_ids = get_forklift_ids()

    # Count by status
    status_counts = {
        'active': 0,
        'charging': 0,
        'maintenance': 0,
        'error': 0,
        'unknown': 0
    }

    low_battery_count = 0
    total_count = 0

    for forklift_id in forklift_ids:
        df = get_forklift_data(forklift_id)
        if df is not None and not df.empty:
            latest = df.iloc[-1]
            forklift_env = latest.get('environment', 'indoor')

            # Apply environment filter
            if env != 'all' and forklift_env != env:
                continue

            status = latest.get('status', 'unknown')
            battery = latest.get('battery_level', 0)

            status_counts[status] += 1
            if battery < 20:
                low_battery_count += 1
            total_count += 1

    # Create summary table
    table_rows = []
    for status, count in status_counts.items():
        percent = (count / total_count * 100) if total_count > 0 else 0
        table_rows.append(html.Tr([
            html.Td(status.capitalize()),
            html.Td(f"{count} ({percent:.1f}%)")
        ]))

    # Add low battery row
    percent_low = (low_battery_count / total_count * 100) if total_count > 0 else 0
    table_rows.append(html.Tr([
        html.Td("Low Battery (<20%)"),
        html.Td(f"{low_battery_count} ({percent_low:.1f}%)")
    ]))

    return html.Table([
        html.Thead(html.Tr([html.Th("Status"), html.Th("Count")])),
        html.Tbody(table_rows)
    ], style={'width': '100%', 'border': '1px solid black'})


# Update impacts summary
@app.callback(
    Output('recent-impacts', 'children'),
    [Input('stats-interval', 'n_intervals'),
     Input('environment-selector', 'value')]
)
def update_recent_impacts(n, env):
    impacts_df = get_impacts_data()
    if impacts_df is None or impacts_df.empty:
        return html.P("No impact data available")

    # Filter by environment if needed
    if env != 'all':
        impacts_df = impacts_df[impacts_df['environment'] == env]

    # Get impacts from the last 24 hours
    cutoff_time = datetime.now() - timedelta(hours=24)
    recent_impacts = impacts_df[impacts_df['timestamp'] > cutoff_time]

    if recent_impacts.empty:
        return html.P("No impacts in the last 24 hours")

    # Create table with recent impacts
    table_rows = []
    for _, impact in recent_impacts.sort_values('timestamp', ascending=False).head(10).iterrows():
        table_rows.append(html.Tr([
            html.Td(impact['forklift_id']),
            html.Td(impact['timestamp'].strftime('%Y-%m-%d %H:%M:%S')),
            html.Td(f"{impact['force_magnitude']:.2f} N"),
            html.Td(impact['environment'])
        ]))

    return html.Div([
        html.P(f"Total impacts in last 24h: {len(recent_impacts)}"),
        html.Table([
            html.Thead(html.Tr([
                html.Th("Forklift ID"),
                html.Th("Timestamp"),
                html.Th("Force"),
                html.Th("Environment")
            ])),
            html.Tbody(table_rows)
        ], style={'width': '100%', 'border': '1px solid black'})
    ])


# Update battery graph
@app.callback(
    Output('battery-graph', 'figure'),
    [Input('battery-interval', 'n_intervals'),
     Input('forklift-selector', 'value'),
     Input('environment-selector', 'value')]
)
def update_battery_graph(n, selected_forklift, env):
    fig = go.Figure()

    forklift_ids = get_forklift_ids()

    for forklift_id in forklift_ids:
        # Skip if not matching selection
        if selected_forklift and forklift_id != selected_forklift:
            continue

        df = get_forklift_data(forklift_id)
        if df is not None and not df.empty:
            # Filter by environment if needed
            forklift_env = df.iloc[-1].get('environment', 'indoor')
            if env != 'all' and forklift_env != env:
                continue

            # Get last 100 battery readings or less
            battery_data = df.tail(100)

            fig.add_trace(go.Scatter(
                x=battery_data['timestamp'],
                y=battery_data['battery_level'],
                mode='lines',
                name=forklift_id
            ))

    fig.update_layout(
        title="Battery Level Over Time",
        xaxis_title="Time",
        yaxis_title="Battery Level (%)",
        yaxis=dict(range=[0, 100]),
        height=500
    )

    # Add threshold line at 20%
    fig.add_shape(
        type="line",
        x0=0,
        y0=20,
        x1=1,
        y1=20,
        line=dict(
            color="red",
            width=2,
            dash="dash",
        ),
        xref="paper",
        yref="y"
    )

    return fig


# Run the app
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8050)