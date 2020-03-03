import os
import re
import datetime
from dateutil.parser import parse as dt_parser

# Parse metadata from filenames in a directory
###########################################
def metadata_parser(data_dir, meta_fields, valid_meta, meta_filters, date_format, 
                    start_date, end_date, error_log, delimiter="_", file_type="png", coprocess=None):
    """Reads metadata the input data directory.

    Args:
        data_dir:     Input data directory.
        meta_fields:  Dictionary of image filename metadata fields and index positions.
        valid_meta:   Dictionary of valid metadata keys.
        meta_filters: Dictionary of metadata filters (key-value pairs).
        date_format:  Date format code for timestamp metadata to use with strptime
        start_date:   Analysis start date in Unix time.
        end_date:     Analysis end date in Unix time.
        error_log:    Error log filehandle object.
        delimiter:    Filename metadata delimiter string or regular expression pattern.
        file_type:    Image filetype extension (e.g. png).
        coprocess:    Coprocess the specified imgtype with the imgtype specified in meta_filters.

    Returns:
        jobcount:     The number of processing jobs.
        meta:         Dictionary of image metadata (one entry per image to be processed).

    :param data_dir: str
    :param meta_fields: dict
    :param valid_meta: dict
    :param meta_filters: dict
    :param date_format: str
    :param start_date: int
    :param end_date: int
    :param error_log: obj
    :param delimiter: str
    :param file_type: str
    :param coprocess: str
    :return jobcount: int
    :return meta: dict
    """

    # Metadata data structure
    meta = {}
    jobcount = 0

    # How many metadata fields are in the files we intend to process?
    meta_count = len(meta_fields.keys())

    # Compile regex (even if it's only a delimiter character)
    regex = re.compile(delimiter)

    # Check whether there is a snapshot metadata file or not
    if os.path.exists(os.path.join(data_dir, "SnapshotInfo.csv")):
        # Open the SnapshotInfo.csv file
        csvfile = open(os.path.join(data_dir, 'SnapshotInfo.csv'), 'r')

        # Read the first header line
        header = csvfile.readline()
        header = header.rstrip('\n')

        # Remove whitespace from the field names
        header = header.replace(" ", "")

        # Table column order
        cols = header.split(',')
        colnames = {}
        for i, col in enumerate(cols):
            colnames[col] = i

        # Read through the CSV file
        for row in csvfile:
            row = row.rstrip('\n')
            data = row.split(',')
            img_list = data[colnames['tiles']]
            if img_list[:-1] == ';':
                img_list = img_list[:-1]
            imgs = img_list.split(';')
            for img in imgs:
                if len(img) != 0:
                    dirpath = os.path.join(data_dir, 'snapshot' + data[colnames['id']])
                    filename = img + '.' + file_type
                    if not os.path.exists(os.path.join(dirpath, filename)):
                        error_log.write("Something is wrong, file {0}/{1} does not exist".format(dirpath, filename))
                        continue
                        # raise IOError("Something is wrong, file {0}/{1} does not exist".format(dirpath, filename))
                    # Metadata from image file name
                    metadata = _parse_filename(filename=img, delimiter=delimiter, regex=regex)
                    # Not all images in a directory may have the same metadata structure only keep those that do
                    if len(metadata) == meta_count:
                        # Image metadata
                        img_meta = {'path': dirpath}
                        img_pass = 1
                        coimg_store = 0
                        # For each of the type of metadata PlantCV keeps track of
                        for field in valid_meta:
                            # If the same metadata is found in the image filename, store the value
                            if field in meta_fields:
                                meta_value = metadata[meta_fields[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match an image value, fail the image
                                    # filter = meta_filters[field]
                                    # if meta_value != filter and (isinstance(filter, list) and not meta_value in field):
                                    filter = meta_filters[field]
                                    if isinstance(filter, list):
                                        if not meta_value in filter:
                                            img_pass = 0
                                    else:
                                        if meta_value != filter:
                                            img_pass = 0
                                img_meta[field] = meta_value
                            # If the same metadata is found in the CSV file, store the value
                            elif field in colnames:
                                meta_value = data[colnames[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match the image value, fail the image
                                    # filter = meta_filters[field]
                                    # if meta_value != filter and (isinstance(field, list) and not meta_value in field):
                                    filter = meta_filters[field]
                                    if isinstance(filter, list):
                                        if not meta_value in filter:
                                            img_pass = 0
                                    else:
                                        if meta_value != filter:
                                            img_pass = 0
                                img_meta[field] = meta_value
                            # Or use the default value
                            else:
                                img_meta[field] = valid_meta[field]["value"]

                        if start_date and end_date and img_meta['timestamp'] is not None:
                            in_date_range = check_date_range(start_date, end_date, img_meta['timestamp'], date_format)
                            if in_date_range is False:
                                img_pass = 0

                        if img_pass:
                            jobcount += 1

                        if coprocess is not None:
                            if img_meta['imgtype'] == coprocess:
                                coimg_store = 1

                        # If the image meets the user's criteria, store the metadata
                        if img_pass == 1:
                            # Link image to coprocessed image
                            coimg_pass = 0
                            if coprocess is not None:
                                for coimg in imgs:
                                    if len(coimg) != 0:
                                        meta_parts = _parse_filename(filename=coimg, delimiter=delimiter, regex=regex)
                                        if len(meta_parts) > 0:
                                            coimgtype = meta_parts[meta_fields['imgtype']]
                                            if coimgtype == coprocess:
                                                if 'camera' in meta_fields:
                                                    cocamera = meta_parts[meta_fields['camera']]
                                                    if 'frame' in meta_fields:
                                                        coframe = meta_parts[meta_fields['frame']]
                                                        if cocamera == img_meta['camera'] and coframe == img_meta['frame']:
                                                            img_meta['coimg'] = coimg + '.' + file_type
                                                            coimg_pass = 1
                                                    else:
                                                        if cocamera == img_meta['camera']:
                                                            img_meta['coimg'] = coimg + '.' + file_type
                                                            coimg_pass = 1
                                                else:
                                                    img_meta['coimg'] = coimg + '.' + file_type
                                                    coimg_pass = 1
                                if coimg_pass == 0:
                                    error_log.write(
                                        "Could not find an image to coprocess with " + os.path.join(dirpath,
                                                                                                    filename) + '\n')
                            meta[filename] = img_meta
                        elif coimg_store == 1:
                            meta[filename] = img_meta
    else:
        # Compile regular expression to remove image file extensions
        pattern = re.escape('.') + file_type + '$'
        ext = re.compile(pattern, re.IGNORECASE)

        # Walk through the input directory and find images that match input criteria
        for (dirpath, dirnames, filenames) in os.walk(data_dir):
            for filename in filenames:
                # Is filename and image?
                is_img = ext.search(filename)
                # If filename is an image, parse the metadata
                if is_img is not None:
                    # Remove the file extension
                    prefix = ext.sub('', filename)
                    metadata = _parse_filename(filename=prefix, delimiter=delimiter, regex=regex)

                    # Not all images in a directory may have the same metadata structure only keep those that do
                    if len(metadata) == meta_count:
                        # Image metadata
                        img_meta = {'path': dirpath}
                        img_pass = 1
                        # For each of the type of metadata PlantCV keeps track of
                        for field in valid_meta:
                            # If the same metadata is found in the image filename, store the value
                            if field in meta_fields:
                                meta_value = metadata[meta_fields[field]]
                                # If the metadata type has a user-provided restriction
                                if field in meta_filters:
                                    # If the input value does not match the image value, fail the image
                                    filter = meta_filters[field]
                                    if meta_value != filter and not meta_value in filter:
                                        img_pass = 0
                                img_meta[field] = meta_value
                            # Or use the default value
                            else:
                                img_meta[field] = valid_meta[field]["value"]

                        if start_date and end_date and img_meta['timestamp'] is not None:
                            in_date_range = check_date_range(start_date, end_date, img_meta['timestamp'], date_format)
                            if in_date_range is False:
                                img_pass = 0

                        # If the image meets the user's criteria, store the metadata
                        if img_pass == 1:
                            meta[filename] = img_meta
                            jobcount += 1

    return jobcount, meta
###########################################


# Check to see if the image was taken between a specified date range
###########################################
def check_date_range(start_date, end_date, img_time, date_format):
    """Check image time versus included date range.

    Args:
        start_date: Start date in Unix time
        end_date:   End date in Unix time
        img_time:   Image datetime
        date_format: date format code for strptime

    :param start_date: int
    :param end_date: int
    :param img_time: str
    :param date_format: str
    :return: bool
    """

    # Convert image datetime to unix time
    try:
        timestamp = datetime.datetime.strptime(img_time, date_format)
    except ValueError as e:
        raise SystemExit(str(e) + '\n  --> Please specify the correct --timestampformat argument <--\n')
    
    time_delta = timestamp - datetime.datetime(1970, 1, 1)
    unix_time = (time_delta.days * 24 * 3600) + time_delta.seconds
    # Does the image date-time fall outside or inside the included range
    if unix_time < start_date or unix_time > end_date:
        return False
    else:
        return True
###########################################


# Filename metadata parser
###########################################
def _parse_filename(filename, delimiter, regex):
    """Parse the input filename and return a list of metadata.

    Args:
        filename:   Filename to parse metadata from
        delimiter:  Delimiter character to split the filename on
        regex:      Compiled regular expression pattern to process file with

    :param filename: str
    :param delimiter: str
    :param regex: re.Pattern
    :return metadata: list
    """

    # Split the filename on delimiter if it is a single character
    if len(delimiter) == 1:
        metadata = filename.split(delimiter)
    else:
        metadata = re.search(regex, filename)
        if metadata is not None:
            metadata = list(metadata.groups())
        else:
            metadata = []
    return metadata
###########################################

class ParseMatchArg:
    special_characters = ":[],"
    def error_message(self, warning, original_text, idx):
        message_and_original = warning + "\n" + original_text
        point_out_error = " " * idx + "^"
        return message_and_original + "\n" + point_out_error
    def parse(self, match_string):
        """
        Parse the match string and return a dictionary of filters.

        Args:
            match_string: String to be parsed

        :param match_string: str
        """
        tokens, specials, indices = self.tokenize_match_arg(match_string)
        dictionary = self.as_dictionary(tokens, specials, indices, match_string)
        return dictionary
    def tokenize_match_arg(self, match_string):
        """This function recognizes the special characters and
        clumps of normal characters within the match arg. For
        example:
        "id:[1,2]" -> ["id", ":", "[", "1", ",", "2", "]"]
        These intermediate results must be turned into a dictionary
        later.
        """
        out = []
        escaped = False
        active_quotes = []
        quote_symbols = ["'",'"']
        current_item = ""
        specials = []
        indices = []
        def flush_current_item(special, idx):
            nonlocal current_item
            if current_item != "":
                out.append(current_item)
                indices.append(idx)
                specials.append(special)
                current_item = ""
        for idx, char in enumerate(match_string):
            if escaped:
                current_item += char
                escaped = False
            elif char in quote_symbols:
                if char in active_quotes:
                    quote_index = active_quotes.index(char)
                    active_quotes = active_quotes[:quote_index]
                    if quote_index != 0:
                        current_item += char
                else:
                    active_quotes.append(char)
            elif len(active_quotes) == 0:
                if char in self.special_characters:
                    flush_current_item(False, idx)
                    current_item += char
                    flush_current_item(special=True,idx=idx)
                elif char == "\\":
                    escaped = True
                elif char == ",":
                    flush_current_item(False, idx)
                    current_item += char
                    flush_current_item(True, idx)
                else:
                    current_item += char
            else:
                current_item += char
            print("current item", current_item)
        flush_current_item(special=False, idx=idx)
        return out, specials, indices
    def as_dictionary(self, tokens, specials, indices, match_string):
        mode = "expecting_key"
        out = {}
        current_key = ""
        current_value_list = []
        current_value = ""
        def flush_value(current_value):
            nonlocal current_value_list
            current_value_list.append(current_value)
        def flush_key_value():
            nonlocal out
            nonlocal current_key
            nonlocal current_value_list
            if current_key != "":
                if current_key in out:
                    out[current_key].extend(current_value_list)
                else:
                    out[current_key] = current_value_list
                current_value_list = []
                current_key = ""
        for token, special, idx, in zip(tokens, specials, indices):
            if mode == "expecting_key":
                if token in self.special_characters and special:
                    raise ValueError(self.error_message("Expecting key value",
                                                   match_string,
                                                   idx))
                else:
                    current_key = token
                    mode = "expecting_colon"
            elif mode == "expecting_colon" and special:
                if token == ":" and special:
                    mode = "expecting_value"
                else:
                    raise ValueError("Key must be followed by :")
            elif mode == "expecting_value":
                if token in ":,]" and special: #refactor
                    raise ValueError(self.error_message("Empty value",
                                                   match_string,
                                                   idx - 1))
                elif token == "[" and special:
                    mode = "list_value"
                else:
                    flush_value(token)
                    flush_key_value()
                    mode = "expecting_key_comma"
            elif mode == "list_value":
                if token == ":" and special:
                    raise ValueError(self.error_message("Cannot use key-value pairs in a list value",
                                                   match_string,
                                                   idx))
                elif token == "]" and special:
                    if len(current_value_list) == 0:
                        raise ValueError(self.error_message("Empty list",
                                                       match_string,
                                                       idx))
                    else:
                        raise ValueError(self.error_message("Empty list item",
                                                       match_string,
                                                       idx))
                else:
                    flush_value(token)
                    mode = "list_comma"
            elif mode == "list_comma":
                if token == "]" and special:
                    flush_key_value()
                    mode = "expecting_key_comma"
                elif token == "," and special:
                    mode = "list_value"
                else:
                    raise ValueError(self.error_message("Expecting comma between list items",
                                                   match_string,
                                                   idx))
            elif mode == "expecting_key_comma":
                if not (token == "," and special):
                    raise ValueError(self.error_message("Expecting comma after value",
                                                   match_string,
                                                   idx))
                mode = "expecting_key"
        flush_key_value()
        return out