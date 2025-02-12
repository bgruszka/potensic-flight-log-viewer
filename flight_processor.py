import os
import re
import shutil
import glob
from zipfile import ZipFile
from datetime import datetime
import tempfile
from flight_data_parser import FlightDataParser

class FlightProcessor:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()
        self.log_dir = 'uploads'
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

    def process_flight_data(self, zip_file):
        """Process uploaded ZIP file containing flight data."""
        try:
            if not os.path.exists(zip_file):
                return {'status': 'error', 'message': 'Upload file not found'}

            original_zip_basename = os.path.basename(zip_file)
            drone_model = self._extract_drone_model(original_zip_basename)
            
            # Process the ZIP file
            try:
                flight_data = self._process_zip_file(zip_file, drone_model)
            except Exception as e:
                import traceback
                stack_trace = traceback.format_exc()
                return {'status': 'error', 'message': f'Error extracting ZIP file: {str(e)}', 'stack_trace': stack_trace}
            
            if not flight_data['has_fc']:
                return {'status': 'error', 'message': 'No valid flight data found in the ZIP file'}

            # Parse flight data from FC files
            parser = FlightDataParser()
            fc_files = [f for f in flight_data['processed_files'] if f.endswith('.fc') or ('-FC' in f and f.endswith('.bin'))]
            
            if not fc_files:
                return {'status': 'error', 'message': 'No valid flight controller data found'}

            # Parse the first FC file (we'll handle multiple files later if needed)
            fc_file_path = os.path.join(self.log_dir, fc_files[0])
            if not os.path.exists(fc_file_path):
                return {'status': 'error', 'message': 'Flight controller file not found'}

            try:
                parsed_data = parser.parse_flight_data(fc_file_path)
            except Exception as e:
                import traceback
                stack_trace = traceback.format_exc()
                return {'status': 'error', 'message': f'Error parsing flight data: {str(e)}', 'stack_trace': stack_trace}
            
            if parsed_data['status'] == 'error':
                return parsed_data

            # Clean up processed files after successful parsing
            self._cleanup_processed_files(flight_data['processed_files'])
            os.remove(zip_file)  # Remove the original ZIP file

            return {
                'status': 'success',
                'drone_model': drone_model,
                'import_date': datetime.now().isoformat(),
                'flight_data': parsed_data
            }

        except Exception as e:
            import traceback
            stack_trace = traceback.format_exc()
            return {'status': 'error', 'message': f'Unexpected error during processing: {str(e)}', 'stack_trace': stack_trace}
        finally:
            self._cleanup()

    def _extract_drone_model(self, zip_basename):
        """Extract drone model from ZIP filename."""
        model = re.sub(r"[0-9]*-(.*)-Drone.*", r"\1", zip_basename)
        return re.sub(r"[^\w]", r" ", model)

    def _process_zip_file(self, zip_file, drone_model):
        """Extract and process files from the ZIP archive."""
        has_fc = False
        processed_files = []

        with ZipFile(zip_file, 'r') as unzip:
            unzip.extractall(path=self.temp_dir)

        fpv_files = []
        for bin_file in glob.glob(os.path.join(self.temp_dir, '**/*'), recursive=True):
            bin_basename = os.path.basename(bin_file)
            bin_type = self._determine_bin_type(bin_basename)

            if bin_type:
                if bin_type == 'FPV':
                    fpv_files.append(bin_file)
                elif bin_type == 'FC':
                    if not has_fc:
                        has_fc = True
                    
                    # Generate unique filename if needed
                    dest_basename = bin_basename
                    dest_path = os.path.join(self.log_dir, dest_basename)
                    while os.path.exists(dest_path):
                        name_parts = os.path.splitext(bin_basename)
                        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                        dest_basename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
                        dest_path = os.path.join(self.log_dir, dest_basename)
                    
                    shutil.copyfile(bin_file, dest_path)
                    processed_files.append(dest_basename)

        # Process FPV files if we have FC data
        if has_fc:
            for fpv_file in fpv_files:
                fpv_basename = os.path.basename(fpv_file)
                # Generate unique filename if needed
                dest_basename = fpv_basename
                dest_path = os.path.join(self.log_dir, dest_basename)
                while os.path.exists(dest_path):
                    name_parts = os.path.splitext(fpv_basename)
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    dest_basename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
                    dest_path = os.path.join(self.log_dir, dest_basename)
                
                shutil.copyfile(fpv_file, dest_path)
                processed_files.append(dest_basename)

        return {'has_fc': has_fc, 'processed_files': processed_files}

    def _determine_bin_type(self, filename):
        """Determine the type of binary file."""
        if '-FPV' in filename and filename.endswith('.bin'):
            return 'FPV'
        elif '-FC' in filename and (filename.endswith('.bin') or filename.endswith('.fc')):
            return 'FC'
        return None

    def _cleanup_processed_files(self, processed_files):
        """Clean up processed files from the uploads directory."""
        for filename in processed_files:
            file_path = os.path.join(self.log_dir, filename)
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception:
                pass

    def _cleanup(self):
        """Clean up temporary files."""
        try:
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass