from IPython.display import display
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pandas.io.sql as psql
import psycopg2
import seaborn as sns

import credentials

conn = psycopg2.connect(database=credentials.database,
                        user=credentials.user,
                        password=credentials.password,
                        host=credentials.host
                       )
conn.autocommit = True

def get_histogram_values(table_name, column_name, nbins=0, bin_width=0, cast_as=None, where_clause=''):
    """
    Takes a SQL table and creates histogram bin heights.
    Relevant parameters are either the number of bins
    or the width of each bin. Only one of these is specified.
    The other one must be left at its default value of 0
    or it will throw an error.
    
    Inputs:
    table_name - Name of the table in SQL
    column_name - Name of the column of interest
    nbins - Number of desired bins (Default: 0)
    bin_width - Width of each bin (Default: 0)
    
    If nbins and bin_width are left at 0, then nbins will
    be set to 25.
    
    cast_as - SQL type to cast as
    where_clause - A SQL where clause specifying any
                   filters
    """
    
    # Look for input errors
    if nbins != 0 and bin_width != 0:
        raise Exception('Both nbins and bin_width cannot be specified. Leave one at 0')
    elif bin_width < 0:
        raise Exception('bin_width must be positive.')
    elif nbins < 0:
        raise Exception('nbins must be positive.')
    elif nbins == 0 and bin_width == 0:
        # Default value if no options are specified
        nbins=25
        
    sql = '''
    SELECT column_name, data_type
      FROM information_schema.columns
     WHERE table_name = '{table_name}'
       AND column_name = '{column_name}'
    '''.format(table_name=table_name, column_name=column_name)
    info_df = psql.read_sql(sql, conn)
    
    if column_name in info_df['column_name'].tolist():
        if cast_as is None:
            is_category = (info_df[info_df.column_name == column_name]['data_type'] == 'text')[0]
        elif cast_as in ['timestamp', 'date', 'int', 'float', 'numeric']:  # If we want to cast it to a number
            is_category = False
        else:
            is_category = True
    else:
        raise Exception(column_name + ' is not found in the table ' + table_name)
    
    # If cast_as is specified, we must create a cast string
    # to recast our columns. If not, we set it as a blank string.
    if cast_as is None:
        cast_string = ''
    else:
        cast_string = '::' + cast_as.upper()
    
    if is_category:
        sql = '''
        SELECT {column_name} AS category, COUNT(*) AS freq
          FROM {table_name}
         GROUP BY {column_name}
         ORDER BY COUNT(*) DESC;
        '''.format(column_name=column_name, table_name=table_name)
    
    else:
        def _min_max_value(column_name):
            sql = '''
            SELECT MIN({col_name}{cast_as}), MAX({col_name}{cast_as})
              FROM {table_name}
             {where_clause};
            '''.format(col_name = column_name,
                       cast_as = cast_string,
                       table_name = table_name,
                       where_clause = where_clause
                      )
            return tuple(psql.read_sql(sql, conn).iloc[0])
        
        # Get min and max value of the column
        min_val, max_val = _min_max_value(column_name)
        
        # Get the span of the column
        span_value = max_val - min_val
        if bin_width == 0:
            bin_width = span_value/nbins
        if nbins == 0:
            nbins = span_value * bin_width
        
        # Form the SQL statement. The min_val must be taken
        # down by a small value because of rounding errors. 
        # If this is not taken into account, a column value
        # may be smaller than the min_value. We also must
        # deal with cases where the column name equals the max
        sql = '''
          WITH binned_table
            AS (SELECT FLOOR(({column_name}{cast_as} - {min_val})
                             /({max_val} - {min_val}) 
                             * {nbins}
                            )
                       /{nbins} * ({max_val} - {min_val}) 
                       + {min_val} AS bin_nbr
                  FROM {table_name}
                 {where_clause}
               )
        SELECT bin_nbr, COUNT(*) AS freq
          FROM binned_table
         GROUP BY bin_nbr
         ORDER BY bin_nbr;
        '''.format(column_name = column_name,
                   cast_as = cast_string,
                   nbins = nbins,
                   min_val = min_val - 1e-8,
                   max_val = max_val + 1e-8,
                   table_name = table_name,
                   where_clause = where_clause
                  )
    
    return psql.read_sql(sql, conn)

def get_scatterplot_values(table_name, column_name_x, column_name_y, nbins=(0, 0), bin_size=(0, 0), cast_x_as=None, cast_y_as=None):
    """
    Takes a SQL table and creates scatter plot bin values.
    This is the 2D version of get_histogram_values.
    Relevant parameters are either the number of bins
    or the size of each bin in both the x and y direction. 
    Only number of bins or size of the bins is specified.
    The other pair must be left at its default value of 0
    or it will throw an error.
    
    Inputs:
    table_name - Name of the table in SQL
    column_name - Name of the column of interest
    nbins - Number of desired bins for x and y directions (Default: (0, 0))
    bin_size - Size of each bin for x and y directions (Default: (0, 0))
    
    If nbins and bin_size are both left at (0, 0), then nbins will be
    set to (1000, 1000)
    
    cast_x_as - SQL type to cast x as
    cast_y_as - SQL type to cast y as
    """
    
    # Look for input errors
    if nbins != (0, 0) and bin_size != (0, 0):
        raise Exception('Both nbins and bin_size cannot be specified. Leave one at (0, 0).')
    elif bin_size[0] < 0 or bin_size[1] < 0:
        raise Exception('Bin dimensions must both be positive.')
    elif nbins[0] < 0 or nbins[1] < 0:
        raise Exception('Number of bin dimensions must both be positive')
    elif nbins == (0, 0) and bin_size == (0, 0):
        # Default value if no options are specified
        nbins = (1000, 1000)
    
    # If cast_x_as or cast_y_as is specified, we must create cast
    # strings to recast our columns. If not, we set them as 
    # blank strings.
    if cast_x_as is None:
        cast_x_string = ''
    else:
        cast_x_string = '::' + cast_x_as.upper()
        
    if cast_y_as is None:
        cast_y_string = ''
    else:
        cast_y_string = '::' + cast_y_as.upper()
        
    def _min_max_value(column_name, cast_as):
        sql = '''
        SELECT MIN({col_name}{cast_as}), MAX({col_name}{cast_as})
          FROM {table_name};
        '''.format(col_name=column_name, table_name=table_name, cast_as=cast_as)
        return tuple(psql.read_sql(sql, conn).iloc[0])
    
    # Get the min and max values for x and y directions
    min_val_x, max_val_x = _min_max_value(column_name_x, cast_as=cast_x_string)
    min_val_y, max_val_y = _min_max_value(column_name_y, cast_as=cast_y_string)
    
    # Get the span of values in the x and y direction
    span_values = (max_val_x - min_val_x, max_val_y - min_val_y)
    
    # Since the bins are generated using nbins, 
    # if only bin_size is specified, we can 
    # back calculate the number of bins that will
    # be used.
    if nbins == (0, 0):
        nbins = [i/j for i, j in zip(span_values, bin_size)]
    
    sql = '''
      WITH binned_table
        AS (SELECT FLOOR(({x_col}{cast_x_as} - {min_val_x})
                         /({max_val_x} - {min_val_x}) 
                         * {nbins_x}
                         )
                   /{nbins_x} * ({max_val_x} - {min_val_x}) 
                   + {min_val_x} AS bin_nbr_x,
                   FLOOR(({y_col}{cast_y_as} - {min_val_y})
                         /({max_val_y} - {min_val_y}) 
                         * {nbins_y}
                         )
                   /{nbins_y} * ({max_val_y} - {min_val_y}) 
                   + {min_val_y} AS bin_nbr_y
              FROM {table_name}
             WHERE {x_col} IS NOT NULL
               AND {y_col} IS NOT NULL
           )
    SELECT bin_nbr_x, bin_nbr_y, COUNT(*) AS freq
      FROM binned_table
     GROUP BY bin_nbr_x, bin_nbr_y
     ORDER BY bin_nbr_x, bin_nbr_y;
    '''.format(x_col = column_name_x,
               cast_x_as = cast_x_string,
               y_col = column_name_y,
               cast_y_as = cast_y_string,
               min_val_x = min_val_x - 1e-8,
               max_val_x = max_val_x + 1e-8,
               min_val_y = min_val_y - 1e-8,
               max_val_y = max_val_y + 1e-8,
               nbins_x = nbins[0],
               nbins_y = nbins[1],
               table_name = table_name
              )
    
    return psql.read_sql(sql, conn)

def _create_weight_percentage(hist_col, normed=False):
    """Convert frequencies to percent"""
    if normed:
        return hist_col/hist_col.sum()
    else:
        return hist_col

def plot_numeric_hists(df_list, labels=[], nbins=10, log=False, normed=False, null_at='left', color_palette=sns.color_palette('deep')):
    """
    Plots numerical histograms together. 
    
    Inputs:
    df_list - A pandas DataFrame or a list of DataFrames
                which have two columns (bin_nbr and freq).
                The bin_nbr is the value of the histogram bin
                and the frequency is how many values fall in
                that bin.
    labels - A string (for one histogram) or list of strings
             which sets the labels for the histograms
    nbins - The desired number of bins
    log - Boolean of whether to display y axis on log scale
          (Default: False)
    normed - Boolean of whether to normalize histograms so
             that the heights of each bin sum up to 1. This
             is useful for plotting columns with difference
             sizes (Default: False)
    null_at - Which side to set a null value column. Options
              are 'left' or 'right'. Leave it empty to not
              include (Default: left)
    """
    
    def _check_for_nulls(df_list):
        """Returns whether any of the DataFrames have a null column."""
        return [df['bin_nbr'].isnull().any() for df in df_list]

    def _add_weights_column(df_list, normed):
        """
        Add the weights column for each DataFrame in a 
        list of DataFrames.
        """
        for df in df_list:
            df['weights'] = _create_weight_percentage(df[['freq']], normed)

    def _get_null_weights(df_list):
        """
        If there are nulls, determine the weights.
        Otherwise, set to 0. Return the list of 
        null weights
        """
        return [float(df[df['bin_nbr'].isnull()].weights)
                if is_null else 0 
                for is_null, df in zip(has_null, df_list)]

    def _plot_hist(bin_nbrs, weights, labels, bins, log):
        """
        Plots the histogram for non-null values with corresponding
        labels if provided. This function will take also reduce the
        number of bins in the histogram. This is useful if we want to
        apply get_histogram_values for a large number of bins, then 
        experiment with plotting different bing amounts using the histogram
        values.
        """
        if len(labels) > 0:
            _, bins, _ = plt.hist(x=bin_nbrs, weights=weights, label=labels, bins=nbins, log=log)
        else:
            _, bins, _ = plt.hist(x=bin_nbrs, weights=weights, bins=nbins, log=log)
        return bins

    def _get_bin_width():
        """Returns each bin width based on number of histograms"""
        if len(df_list) == 1:
            return 1
        else:
            return 0.8/num_hists

    def _get_null_bin_width():
        """Returns the width of each null bin."""
        bin_width = bins[1] - bins[0]
        if num_hists == 1:
            return bin_width
        else:
            return 0.8 * bin_width/len(null_weights)

    def _get_null_bin_left(loc):
        """Gets the left index/indices or the null column(s)."""
        bin_width = bins[1] - bins[0]
        if loc == 'left':
            if num_hists == 1:
                return [bins[0] - bin_width]
            else:
                return [bins[0] - bin_width + bin_width*0.1 + i*_get_null_bin_width() for i in range(num_hists)]
        elif loc == 'right':
            if num_hists == 1:
                return [bins[-1]]
            else:
                return [bin_width*0.1 + i*_get_null_bin_width() + bins[-1] for i in range(num_hists)]
   
    def _plot_null_xticks(loc, xticks):
        """Given current xticks, plot appropriate NULL tick."""
        bin_width = bins[1] - bins[0]
        if loc == 'left':
            plt.xticks([bins[0] - bin_width*0.5] + xticks[1:].tolist(), ['NULL'] + [int(i) for i in xticks[1:]])
        elif loc == 'right':
            plt.xticks(xticks[:-1].tolist() + [bins[-1] + bin_width*0.5], [int(i) for i in xticks[:-1]] + ['NULL'])

    # If df_list is a DataFrame, convert it into a list
    # If it is a list, keep it as is
    if str(type(df_list)) == "<class 'pandas.core.frame.DataFrame'>":
        df_list = [df_list]
    # If labels is a string, convert it to a list
    # If it is a list, keep it as is
    if type(labels) == "<type 'str'>":
        labels = [labels]

    # Number of histograms we want to overlay
    num_hists = len(df_list)

    # If any of the columns are null
    has_null = _check_for_nulls(df_list)
    _add_weights_column(df_list, normed)

    # Set color_palette
    sns.set_palette(color_palette)
    null_weights = _get_null_weights(df_list)
    
    df_list = [df.dropna() for df in df_list]
    weights = [df.weights for df in df_list]
    bin_nbrs = [df.bin_nbr for df in df_list]
    
    # Plot histograms and retrieve bins
    bins = _plot_hist(bin_nbrs, weights, labels, nbins, log)

    null_bin_width = _get_null_bin_width()
    null_bin_left = _get_null_bin_left(null_at)
    xticks, _ = plt.xticks()

    # If there are any NULLs, plot them and change xticks
    if np.any(has_null):
        for i in range(num_hists):
            plt.bar(null_bin_left[i], null_weights[i], null_bin_width, color=color_palette[i], hatch='x')
        _plot_null_xticks(null_at, xticks)

def plot_categorical_hists(df_list, labels=[], log=False, normed=False, null_at='left', order_by=0, ascending=True, color_palette=sns.color_palette('deep')):
    """
    Plots categorical histograms
    
    Inputs:
    df_list - A pandas DataFrame or a list of DataFrames
                which have two columns (bin_nbr and freq).
                The bin_nbr is the value of the histogram bin
                and the frequency is how many values fall in that
                bin.
    labels - A string (for one histogram) or list of strings
             which sets the labels for the histograms
    log - Boolean of whether to display y axis on log scale
          (Default: False)
    normed - Boolean of whether to normalize histograms so
             that the heights of each bin sum up to 1. This
             is useful for plotting columns with difference
             sizes (Default: False)
    null_at - Which side to set a null value column. The options
              are:
              'left' - Put the null on the left side
              'order' - Leave it in its respective order
              'right' - Put it on the right side
              '' - If left blank, leave out              
              (Default: order)
    order_by - How to order the bars. The options are:
               'alphetical' - Orders the categories in alphabetical
                            order
               integer - an integer value denoting for which df_list
                         DataFrame to sort by
    ascending - Boolean of whether to sort values in ascending order 
                (Default: False)
    color_palette - Seaborn colour palette, i.e., a list of tuples
                    representing the colours. 
                    (Default: sns deep color palette)
    """

    def _join_freq_df(df_list):
        """
        Joins all the DataFrames so that we have a master table 
        with category and the frequencies for each table.

        Returns the joined DataFrame
        """
        for i in range(len(df_list)):
            temp_df = df_list[i].copy()
            temp_df.columns = ['category', 'freq_{}'.format(i)]

            # Add weights column (If normed, we must take this into account)
            temp_df['weights_{}'.format(i)] = _create_weight_percentage(temp_df['freq_{}'.format(i)], normed)

            if i == 0:
                df = temp_df
            else:
                df = pd.merge(df, temp_df, how='outer', on='category')

        # Fill in nulls with 0 (except for category column)
        for col in df.columns[1:]:
            df[col] = df[col].fillna(0)
        return df
  
    def _get_num_categories(hist_df):
        """
        Get the number of categories depending on whether
        we are specifying to drop it in the function.
        """
        if null_at == '':
            return hist_df['category'].dropna().shape[0]
        else:
            return hist_df.shape[0]
   
    def _get_bin_order(loc, hist_df, order_by):
        """
        Sorts hist_df by the specified order.
        """
        if order_by == 'alphabetical':
            return hist_df.sort_values('category', ascending=ascending).reset_index(drop=True)
        elif str(type(order_by)) == "<type 'int'>":
            # Desired column in the hist_df DataFrame
            weights_col = 'weights_{}'.format(order_by)

            if weights_col not in hist_df.columns:
                raise Exception('order_by index not in hist_df. ')
            return hist_df.sort_values(weights_col, ascending=ascending).reset_index(drop=True)
        else:
            raise Exception('Invalid order_by')

    def _get_bin_left(loc, hist_df):
        """Returns a list of the locations of the left edges of the bins."""
        
        def _get_within_bin_left(hist_df):
            """
            Each bin has width 1. If there is more than one histogram, 
            each one must fit in this bin of width 1, so 
            Returns indices within a bin for each histogram. This is needed
            since there is no 
            """
            if len(hist_df) == 1:
                return [0, 1]
            else:
                return np.linspace(0.1, 0.9, num_hists + 1)[:-1]

        within_bin_left = _get_within_bin_left(hist_df)


        # For each histogram, we generate a separate list of 
        # tick locations. We do this so that later, when we plot
        # we can use different colours for each.

        # If there are any NULL categories
        if np.sum(hist_df.category.isnull()) > 0:
            if loc == 'left': 
                bin_left = [np.arange(1 + within_bin_left[i], num_categories + within_bin_left[i]).tolist() for i in range(num_hists)]
                null_left = [[within_bin_left[i]] for i in range(num_hists)]
            elif loc == 'right':
                bin_left = [np.arange(within_bin_left[i], num_categories - 1 + within_bin_left[i]).tolist() for i in range(num_hists)]
                # Subtract one from num_categories since num_categories includes
                # the null bin. Subtracting will place the null bin in the proper
                # location.
                null_left = [[num_categories - 1 + within_bin_left[i]] for i in range(num_hists)]
            elif loc == 'order':
                # Get the index of null and non-null categories in hist_df
                null_indices = np.array(hist_df[pd.isnull(hist_df.category)].index)
                non_null_indices = np.array(hist_df.dropna().index)
                bin_left = [(within_bin_left[i] + non_null_indices).tolist() for i in range(num_hists)]
                null_left = [(within_bin_left[i] + null_indices).tolist() for i in range(num_hists)]
            elif loc == '':
                bin_left = [np.arange(within_bin_left[i], num_categories + 1 + within_bin_left[i])[:-1].tolist() for i in range(num_hists)]
                null_left = [[]] * num_hists
        else:
            bin_left = [np.arange(within_bin_left[i], hist_df.dropna().shape[0] + 1 + within_bin_left[i])[:-1].tolist() for i in range(num_hists)]
            null_left = [[]] * num_hists

        return bin_left, null_left

    def _get_bin_height(loc, order_by, hist_df):
        """Returns a list of the heights of the bins and the category order"""

        hist_df_null = hist_df[hist_df.category.isnull()]
        hist_df_non_null = hist_df[~hist_df.category.isnull()]

        # Set the ordering
        if order_by == 'alphabetical':            
            hist_df_non_null = hist_df_non_null.sort_values('category', ascending=ascending)
        else:
            if 'weights_{}'.format(order_by) not in hist_df_non_null.columns:
                raise Exception("Order by number exceeds number of DataFrames.")
            hist_df_non_null = hist_df_non_null.sort_values('weights_{}'.format(order_by), ascending=ascending)

        if log:
            bin_height = [np.log10(hist_df_non_null['weights_{}'.format(i)]).tolist() for i in range(num_hists)]
        else:
            bin_height = [hist_df_non_null['weights_{}'.format(i)].tolist() for i in range(num_hists)]

        # If loc is '', then we do not want a NULL height
        # since we are ignoring NULL values
        if loc == '':
            null_height = [[]] * num_hists
        else:
            if log:
                null_height = [np.log10(hist_df_null['weights_{}'.format(i)]).tolist() for i in range(num_hists)]
            else:
                null_height = [hist_df_null['weights_{}'.format(i)].tolist() for i in range(num_hists)]

        return bin_height, null_height

    def _get_bin_width():
        """Returns each bin width based on number of histograms"""
        if len(df_list) == 1:
            return 1
        else:
            return 0.8/num_hists

    def _plot_all_histograms(bin_left, bin_height, bin_width):
        for i in range(num_hists):
            # If there are any null bins, plot them
            if len(null_bin_height[i]) > 0:
                plt.bar(null_bin_left[i], null_bin_height[i], bin_width, hatch='x', color=color_palette[i])
            plt.bar(bin_left[i], bin_height[i], bin_width, color=color_palette[i])

    def _plot_xticks(loc, bin_left, hist_df):
        # If there are any NULL categories
        if np.sum(hist_df.category.isnull()) > 0:
            if loc == 'left':
                xticks_loc = np.arange(num_categories) + 0.5
                plt.xticks(xticks_loc, ['NULL'] + hist_df.dropna()['category'].tolist(), rotation=90)
            elif loc == 'right':
                xticks_loc = np.arange(num_categories) + 0.5
                plt.xticks(xticks_loc, hist_df.dropna()['category'].tolist() + ['NULL'], rotation=90)
            elif loc == 'order':
                xticks_loc = np.arange(num_categories) + 0.5
                plt.xticks(xticks_loc, hist_df['category'].fillna('NULL').tolist(), rotation=90)
            elif loc == '':
                xticks_loc = np.arange(num_categories) + 0.5
                plt.xticks(xticks_loc, hist_df.dropna()['category'].tolist(), rotation=90)
        else:
            xticks_loc = np.arange(num_categories) + 0.5
            plt.xticks(xticks_loc, hist_df.dropna()['category'].tolist(), rotation=90)

    def _plot_new_yticks():
        """Changes yticks to log scale."""
        max_y_tick = int(np.ceil(np.max(bin_height))) + 1
        yticks = [10**i for i in range(max_y_tick)]
        yticks = ['1e{}'.format(i) for i in range(max_y_tick)]
        plt.yticks(range(max_y_tick), yticks)


    # If df_list is a DataFrame, convert it into a list
    # If it is a list, keep it as is
    if str(type(df_list)) == "<class 'pandas.core.frame.DataFrame'>":
        df_list = [df_list]
    # If labels is a string, convert it to a list
    # If it is a list, keep it as is
    if type(labels) == "<type 'str'>":
        labels = [labels]

    # Joins in all the df_list DataFrames
    # so that we can pick a certain category
    # and retrieve the count for each.
    hist_df = _join_freq_df(df_list)
    # Order them based on specified order
    hist_df = _get_bin_order(null_at, hist_df, order_by)

    num_hists = len(df_list)
    num_categories = _get_num_categories(hist_df)

    bin_left, null_bin_left = _get_bin_left(null_at, hist_df)
    bin_height, null_bin_height = _get_bin_height(null_at, order_by, hist_df)
    bin_width = _get_bin_width()

    # Plotting functions
    _plot_all_histograms(bin_left, bin_height, bin_width)
    _plot_xticks(null_at, bin_left, hist_df)
    if log:
        _plot_new_yticks()


        