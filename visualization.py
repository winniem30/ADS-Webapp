"""
Visualization module for Money Laundering Detection Platform
Handles chart generation, graphs, and visual analytics
"""

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import networkx as nx
import pandas as pd
import numpy as np
import os
from config import Config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VisualizationEngine:
    """Handles all visualization and chart generation"""
    
    def __init__(self):
        """Initialize visualization engine"""
        self.charts_folder = Config.CHARTS_FOLDER
        os.makedirs(self.charts_folder, exist_ok=True)
        
        # Set style
        sns.set_style("whitegrid")
        plt.rcParams['figure.figsize'] = (12, 8)
    
    def create_spider_chart(self, spider_features, dataset_type='dataset1', title="Risk Analysis Spider Chart"):
        """
        Create interactive spider/radar chart for risk analysis with dataset-specific axes
        
        Args:
            spider_features: Dictionary of feature values (0-100)
            dataset_type: 'dataset1' or 'dataset2' to determine axes
            title: Chart title
            
        Returns:
            dict: Chart data for Plotly
        """
        # Select appropriate axes based on dataset type
        if dataset_type == 'dataset1':
            axes = Config.DATASET1_SPIDER_AXES
        elif dataset_type == 'dataset2':
            axes = Config.DATASET2_SPIDER_AXES
        elif dataset_type == 'simple':
            axes = Config.SIMPLE_SPIDER_AXES
        elif dataset_type == 'synthetic_ml':
            axes = Config.SYNTHETIC_ML_SPIDER_AXES
        else:
            # Default to Dataset 1 axes if unknown
            axes = Config.DATASET1_SPIDER_AXES
        
        values = [spider_features.get(axis, 50) for axis in axes]
        
        # Close the loop
        values += values[:1]
        axes += axes[:1]
        
        fig = go.Figure(data=go.Scatterpolar(
            r=values,
            theta=axes,
            fill='toself',
            name='Risk Profile',
            line_color='rgb(220, 53, 69)',
            fillcolor='rgba(220, 53, 69, 0.3)'
        ))
        
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    ticks=dict(font=dict(size=10))
                )
            ),
            showlegend=True,
            title=title,
            font=dict(size=12),
            height=500,
            width=600
        )
        
        # Save as HTML
        chart_path = os.path.join(self.charts_folder, f"spider_{dataset_type}_{hash(title)}.html")
        fig.write_html(chart_path)
        
        # Also save as PNG
        png_path = os.path.join(self.charts_folder, f"spider_{dataset_type}_{hash(title)}.png")
        fig.write_image(png_path)
        
        return {
            'html': chart_path,
            'png': png_path,
            'data': fig.to_json(),
            'axes': axes[:-1]  # Return axes without the duplicate
        }
    
    def create_bar_chart(self, data, x_col, y_col, title="Bar Chart", color_col=None):
        """
        Create bar chart
        
        Args:
            data: DataFrame with data
            x_col: X-axis column
            y_col: Y-axis column
            title: Chart title
            color_col: Column for color coding
            
        Returns:
            dict: Chart data
        """
        if color_col:
            fig = px.bar(data, x=x_col, y=y_col, color=color_col, title=title)
        else:
            fig = px.bar(data, x=x_col, y=y_col, title=title)
        
        fig.update_layout(
            xaxis_title=x_col,
            yaxis_title=y_col,
            font=dict(size=12)
        )
        
        chart_path = os.path.join(self.charts_folder, f"bar_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_pie_chart(self, data, names_col, values_col, title="Pie Chart"):
        """
        Create pie chart
        
        Args:
            data: DataFrame with data
            names_col: Column for slice names
            values_col: Column for slice values
            title: Chart title
            
        Returns:
            dict: Chart data
        """
        fig = px.pie(data, names=names_col, values=values_col, title=title)
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
        chart_path = os.path.join(self.charts_folder, f"pie_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_line_chart(self, data, x_col, y_col, title="Line Chart", color_col=None):
        """
        Create line chart
        
        Args:
            data: DataFrame with data
            x_col: X-axis column
            y_col: Y-axis column
            title: Chart title
            color_col: Column for color coding
            
        Returns:
            dict: Chart data
        """
        if color_col:
            fig = px.line(data, x=x_col, y=y_col, color=color_col, title=title)
        else:
            fig = px.line(data, x=x_col, y=y_col, title=title)
        
        fig.update_layout(
            xaxis_title=x_col,
            yaxis_title=y_col,
            font=dict(size=12)
        )
        
        chart_path = os.path.join(self.charts_folder, f"line_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_heatmap(self, data, title="Heatmap"):
        """
        Create heatmap
        
        Args:
            data: DataFrame or correlation matrix
            title: Chart title
            
        Returns:
            dict: Chart data
        """
        if isinstance(data, pd.DataFrame):
            # Calculate correlation if not already a correlation matrix
            if data.max().max() <= 1 and data.min().min() >= -1:
                corr_matrix = data
            else:
                corr_matrix = data.corr()
        else:
            corr_matrix = data
        
        fig = px.imshow(corr_matrix, 
                       text_auto=True, 
                       aspect="auto",
                       title=title,
                       color_continuous_scale='RdBu_r')
        
        chart_path = os.path.join(self.charts_folder, f"heatmap_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_network_graph(self, transactions, max_nodes=50):
        """
        Create network graph showing transaction relationships
        
        Args:
            transactions: DataFrame with transaction data
            max_nodes: Maximum number of nodes to display
            
        Returns:
            dict: Network graph data
        """
        G = nx.Graph()
        
        # Add nodes and edges
        for _, row in transactions.head(max_nodes).iterrows():
            sender = row.get('sender', 'Unknown')
            receiver = row.get('receiver', 'Unknown')
            amount = row.get('amount', 0)
            risk_level = row.get('risk_level', 'unknown')
            
            G.add_node(sender, type='sender')
            G.add_node(receiver, type='receiver')
            G.add_edge(sender, receiver, weight=amount, risk=risk_level)
        
        # Calculate layout
        pos = nx.spring_layout(G, k=1, iterations=50)
        
        # Create node traces
        node_x = []
        node_y = []
        node_text = []
        node_color = []
        
        for node in G.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_text.append(node)
            
            # Color based on node type
            if G.nodes[node]['type'] == 'sender':
                node_color.append('rgb(54, 162, 235)')
            else:
                node_color.append('rgb(255, 99, 132)')
        
        # Create edge traces
        edge_x = []
        edge_y = []
        
        for edge in G.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
        
        # Create figure
        fig = go.Figure()
        
        # Add edges
        fig.add_trace(go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=0.5, color='#888'),
            hoverinfo='none',
            mode='lines'
        ))
        
        # Add nodes
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y,
            mode='markers',
            hoverinfo='text',
            text=node_text,
            marker=dict(
                size=10,
                color=node_color,
                line=dict(width=2, color='DarkSlateGrey')
            )
        ))
        
        fig.update_layout(
            title='Transaction Network Analysis',
            showlegend=False,
            hovermode='closest',
            margin=dict(b=20,l=5,r=5,t=40),
            annotations=[ dict(
                text="Transaction Network",
                showarrow=False,
                xref="paper", yref="paper",
                x=0.005, y=-0.002 ) ],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False)
        )
        
        chart_path = os.path.join(self.charts_folder, "network_graph.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json(),
            'node_count': len(G.nodes()),
            'edge_count': len(G.edges())
        }
    
    def create_feature_importance_chart(self, feature_importance, top_n=15):
        """
        Create horizontal bar chart for feature importance
        
        Args:
            feature_importance: Dictionary of feature importance scores
            top_n: Number of top features to display
            
        Returns:
            dict: Chart data
        """
        # Sort and get top features
        sorted_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:top_n]
        features = [f[0] for f in sorted_features]
        importance = [f[1] for f in sorted_features]
        
        fig = go.Figure(go.Bar(
            x=importance,
            y=features,
            orientation='h',
            marker_color='rgb(55, 83, 109)'
        ))
        
        fig.update_layout(
            title='Feature Importance',
            xaxis_title='Importance Score',
            yaxis_title='Features',
            height=400 + top_n * 20,
            margin=dict(l=200)
        )
        
        chart_path = os.path.join(self.charts_folder, "feature_importance.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_risk_distribution_chart(self, data):
        """
        Create risk distribution visualization
        
        Args:
            data: DataFrame with risk_level column
            
        Returns:
            dict: Chart data
        """
        risk_counts = data['risk_level'].value_counts()
        
        colors = [Config.RISK_COLORS.get(level, '#6c757d') for level in risk_counts.index]
        
        fig = go.Figure(data=[
            go.Bar(
                x=risk_counts.index,
                y=risk_counts.values,
                marker_color=colors
            )
        ])
        
        fig.update_layout(
            title='Risk Distribution',
            xaxis_title='Risk Level',
            yaxis_title='Count',
            showlegend=False
        )
        
        chart_path = os.path.join(self.charts_folder, "risk_distribution.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_time_series_chart(self, data, date_col, value_col, title="Time Series"):
        """
        Create time series chart
        
        Args:
            data: DataFrame with time series data
            date_col: Date column name
            value_col: Value column name
            title: Chart title
            
        Returns:
            dict: Chart data
        """
        data = data.copy()
        data[date_col] = pd.to_datetime(data[date_col])
        data = data.sort_values(date_col)
        
        fig = px.line(data, x=date_col, y=value_col, title=title)
        fig.update_layout(
            xaxis_title='Date',
            yaxis_title=value_col
        )
        
        chart_path = os.path.join(self.charts_folder, f"timeseries_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_gauge_chart(self, value, title="Risk Score", max_value=100):
        """
        Create gauge chart for risk score
        
        Args:
            value: Risk score value
            title: Chart title
            max_value: Maximum value for gauge
            
        Returns:
            dict: Chart data
        """
        fig = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = value,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': title},
            gauge = {
                'axis': {'range': [None, max_value]},
                'bar': {'color': "darkblue"},
                'steps': [
                    {'range': [0, 20], 'color': "lightgreen"},
                    {'range': [20, 40], 'color': "lightblue"},
                    {'range': [40, 60], 'color': "yellow"},
                    {'range': [60, 80], 'color': "orange"},
                    {'range': [80, 100], 'color': "red"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': 80
                }
            }
        ))
        
        chart_path = os.path.join(self.charts_folder, f"gauge_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_dashboard_charts(self, stats_data):
        """
        Create multiple charts for dashboard
        
        Args:
            stats_data: Dictionary with dashboard statistics
            
        Returns:
            dict: All dashboard charts
        """
        charts = {}
        
        # Risk distribution pie chart
        if 'risk_distribution' in stats_data:
            risk_df = pd.DataFrame(list(stats_data['risk_distribution'].items()), 
                                   columns=['risk_level', 'count'])
            charts['risk_pie'] = self.create_pie_chart(risk_df, 'risk_level', 'count', 
                                                       'Risk Distribution')
        
        # Prediction distribution bar chart
        if 'prediction_distribution' in stats_data:
            pred_df = pd.DataFrame(list(stats_data['prediction_distribution'].items()),
                                   columns=['prediction', 'count'])
            charts['prediction_bar'] = self.create_bar_chart(pred_df, 'prediction', 'count',
                                                              'Prediction Distribution')
        
        return charts
    
    def create_model_comparison_chart(self, comparison_data):
        """
        Create model comparison charts
        
        Args:
            comparison_data: Dictionary with model comparison results
            
        Returns:
            dict: Comparison charts
        """
        charts = {}
        
        # Prepare data
        models = list(comparison_data.keys())
        metrics = ['execution_time', 'mean_probability', 'fraud_rate']
        
        for metric in metrics:
            values = [comparison_data[model].get(metric, 0) for model in models]
            
            fig = go.Figure(data=[
                go.Bar(name=metric, x=models, y=values)
            ])
            
            fig.update_layout(
                title=f'Model Comparison - {metric}',
                xaxis_title='Model',
                yaxis_title=metric
            )
            
            chart_path = os.path.join(self.charts_folder, f"model_comparison_{metric}.html")
            fig.write_html(chart_path)
            
            charts[metric] = {
                'html': chart_path,
                'data': fig.to_json()
            }
        
        return charts
    
    def create_treemap(self, data, path_col, value_col, title="Treemap"):
        """
        Create treemap visualization
        
        Args:
            data: DataFrame with data
            path_col: Column for hierarchy path
            value_col: Column for values
            title: Chart title
            
        Returns:
            dict: Chart data
        """
        fig = px.treemap(data, path=[path_col], values=value_col, title=title)
        
        chart_path = os.path.join(self.charts_folder, f"treemap_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def create_area_chart(self, data, x_col, y_col, title="Area Chart"):
        """
        Create area chart
        
        Args:
            data: DataFrame with data
            x_col: X-axis column
            y_col: Y-axis column
            title: Chart title
            
        Returns:
            dict: Chart data
        """
        fig = px.area(data, x=x_col, y=y_col, title=title)
        
        chart_path = os.path.join(self.charts_folder, f"area_{hash(title)}.html")
        fig.write_html(chart_path)
        
        return {
            'html': chart_path,
            'data': fig.to_json()
        }
    
    def export_chart_as_image(self, chart_data, output_path, format='png'):
        """
        Export chart as image file
        
        Args:
            chart_data: Chart data dictionary
            output_path: Output file path
            format: Image format (png, jpg, svg)
        """
        if 'png' in chart_data and os.path.exists(chart_data['png']):
            import shutil
            shutil.copy(chart_data['png'], output_path)
            logger.info(f"Chart exported to {output_path}")
        else:
            logger.warning("PNG version not available for export")
