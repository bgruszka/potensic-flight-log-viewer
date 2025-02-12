from flask import Flask, render_template, request, flash, redirect, url_for, session
import folium
import os
import logging
import math
import datetime
from werkzeug.utils import secure_filename
from flight_processor import FlightProcessor
from geopy.distance import geodesic
from flask_session import Session

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
app.secret_key = 'your-super-secret-key-123'

# Ensure the uploads directory exists
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Initialize flight processor
flight_processor = FlightProcessor()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/view-map', methods=['POST'])
def view_map():
    try:
        if 'file' not in request.files:
            flash('Error: No file was selected for upload')
            return redirect(url_for('index'))
        
        file = request.files['file']
        if file.filename == '':
            flash('Error: No file was selected for upload')
            return redirect(url_for('index'))
        
        if not file.filename.endswith('.zip'):
            flash('Error: Please upload a ZIP file containing flight records')
            return redirect(url_for('index'))
        
        # Ensure upload directory exists
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        
        # Save the uploaded file
        filename = secure_filename(file.filename)
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # Process the flight data
        result = flight_processor.process_flight_data(file_path)
        
        if result['status'] == 'error':
            error_message = result['message']
            if 'stack_trace' in result:
                app.logger.error(f'Stack trace:\n{result["stack_trace"]}')
                error_message += '\nCheck application logs for stack trace.'
            flash(f'Error processing flight data: {error_message}')
            return redirect(url_for('index'))
        
        # Get flight data from the processed result
        flight_data = {}
        flight_data['points'] = result['flight_data']['points']
        flight_data['home_position'] = result['flight_data']['home_position']
        app.logger.debug(f'Received flight data in POST request: {"present" if flight_data["points"] else "not present"}')
        
        if not flight_data['points']:
            app.logger.warning('No flight data found in request')
            flash('No flight data available. Please upload a flight data file first.')
            return redirect(url_for('index'))
        
        points = flight_data['points']
        home_position = flight_data['home_position']
        app.logger.debug(f'Number of flight points: {len(points)}')
        app.logger.debug(f'Home position: {home_position}')
        
        if not points:
            app.logger.warning('No flight data points available in the processed file')
            flash('No flight data points available in the processed file.')
            return redirect(url_for('index'))
        
        # Create a map centered on the home position or first point
        center_lat = home_position[0] if home_position else points[0]['latitude']
        center_lon = home_position[1] if home_position else points[0]['longitude']
        m = folium.Map(location=[center_lat, center_lon], zoom_start=16)
        
        # Add home position marker if available
        if home_position:
            folium.Marker(
                location=home_position,
                popup='Home Position',
                icon=folium.Icon(color='red', icon='home', prefix='fa')
            ).add_to(m)
        
        # Create flight path with direction indicators
        coordinates = [[p['latitude'], p['longitude']] for p in points]
        # Add arrows to show flight direction
        folium.PolyLine(
            coordinates,
            weight=3,
            color='blue',
            opacity=0.8,
            popup=folium.Popup('Flight Path', show=False),
            tooltip='Flight Path'
        ).add_to(m)

        # Add arrow indicators along the path
        for i in range(0, len(coordinates)-1, max(1, len(coordinates)//5)):
            p1 = coordinates[i]
            p2 = coordinates[i+1]
            # Calculate bearing between points
            bearing = math.degrees(math.atan2(
                p2[1] - p1[1],
                p2[0] - p1[0]
            ))
            folium.RegularPolygonMarker(
                location=[(p1[0] + p2[0])/2, (p1[1] + p2[1])/2],
                number_of_sides=3,
                radius=6,
                rotation=bearing - 90,  # Adjust rotation to point in the direction of travel
                color='blue',
                fill=True,
                opacity=0.8
            ).add_to(m)
        
        # Add start and end markers
        if len(points) > 0:
            start_point = [points[0]['latitude'], points[0]['longitude']]
            end_point = [points[-1]['latitude'], points[-1]['longitude']]
            
            # Calculate distance between start and end points
            try:
                # Validate coordinates before calculating distance
                if not (-90 <= start_point[0] <= 90 and -90 <= end_point[0] <= 90):
                    raise ValueError('Invalid latitude value')
                if not (-180 <= start_point[1] <= 180 and -180 <= end_point[1] <= 180):
                    raise ValueError('Invalid longitude value')
                    
                start_end_distance = geodesic(
                    (start_point[0], start_point[1]),
                    (end_point[0], end_point[1])
                ).meters
                
                if start_end_distance < 20:  # If points are within 20 meters
                    # Create a single marker for both start and end
                    folium.Marker(
                        location=start_point,
                        popup='Takeoff and Landing Position',
                        icon=folium.DivIcon(html=f"""
                            <div style="
                                background-color: #4a90e2;
                                border: 2px solid white;
                                border-radius: 50%;
                                text-align: center;
                                padding: 5px;
                                width: 36px;
                                height: 36px;
                                line-height: 26px;
                                color: white;
                                box-shadow: 0 2px 4px rgba(0,0,0,0.2);
                            ">
                            <i class="fa fa-exchange"></i>
                            </div>
                        """)
                    ).add_to(m)
                else:
                    # Add separate start and end markers
                    folium.Marker(
                        location=start_point,
                        popup='Start',
                        icon=folium.Icon(color='green', icon='play', prefix='fa')
                    ).add_to(m)
                    
                    folium.Marker(
                        location=end_point,
                        popup='End',
                        icon=folium.Icon(color='red', icon='stop', prefix='fa')
                    ).add_to(m)
            except ValueError as e:
                app.logger.warning(f'Invalid coordinates detected: {str(e)}')
                # Skip distance calculation and add separate markers anyway
                folium.Marker(
                    location=start_point,
                    popup='Start',
                    icon=folium.Icon(color='green', icon='play', prefix='fa')
                ).add_to(m)
                
                folium.Marker(
                    location=end_point,
                    popup='End',
                    icon=folium.Icon(color='red', icon='stop', prefix='fa')
                ).add_to(m)
        
        app.logger.info('Successfully generated flight path map')
        map_html = m._repr_html_()
        return render_template('map.html', map=map_html)
        
    except Exception as e:
        import traceback
        stack_trace = traceback.format_exc()
        app.logger.error(f'An unexpected error occurred while processing flight data: {str(e)}\nStack trace:\n{stack_trace}')
        flash(f'An unexpected error occurred while processing flight data: {str(e)}\nCheck application logs for stack trace.')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)