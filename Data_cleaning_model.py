import pandas as pd
import numpy as np


# Cleaning Agents Data
def clean_agents_data(df):
    df = df.drop_duplicates(subset='agent_id', keep='last')

    df['agent_id'] = df['agent_id'].astype(str)
    df['team_id'] = df['team_id'].astype(str)

    df['created_at'] = pd.to_datetime(
        df['created_at'],
        format='mixed',
        errors='coerce'
    )

    df['updated_at'] = pd.to_datetime(
        df['updated_at'],
        format='mixed',
        errors='coerce'
    )

    return df


# Cleaning Interactions Data
df_interactions_2 = pd.read_csv('interactions.csv')
df_agents_2 = pd.read_csv('agents.csv')


def clean_interactions_data(df_interactions, df_agents):

    # 1. Drop duplicates based on interaction_id, keeping the last occurrence
    df_interactions = df_interactions.drop_duplicates(
        subset='interaction_id',
        keep='last'
    )

    df_interactions = df_interactions.dropna(
        subset=['interaction_id'],
        how='any'
    )

    # Channel mapping
    if 'channel' in df_interactions.columns:

        df_interactions['channel'] = df_interactions['channel'].astype(str)

        channel_mapping = {
            'cha': 'Chat',
            'call': 'Call',
            'email': 'Email',
            'e-mail': 'Email',
            'live chat': 'Live Chat',
            'phone': 'Phone',
            'phone call': 'Phone',
            'voice': 'Voice',
            'web chat': 'Web Chat'
        }

        df_interactions['channel'] = (
            df_interactions['channel']
            .str.strip()
            .str.lower()
            .map(channel_mapping)
        )

    # 2. Map the issue_category values using the mapping dictionary
    if 'issue_category' in df_interactions.columns:

        issue_category_mapping = {
            'Technical': 'Technical',
            'Technical Issue': 'Technical',
            'Tech Support': 'Technical',

            'Billing': 'Billing',
            'Biling': 'Billing',
            'billing issue': 'Billing',
            'Billing & Payments': 'Billing',

            'Complaint': 'Complaint',
            'Complaints': 'Complaint',

            'Cancellation': 'Cancellation',
            'Cancel Service': 'Cancellation',

            'Account Access': 'Account Access',
            'Account Acces': 'Account Access',
            'Login/Account': 'Account Access',
            'Account': 'Account Access',

            'Product Inquiry': 'Product Inquiry',
            'Product Enquiry': 'Product Inquiry',
            'Product Info': 'Product Inquiry',

            'Delivery/Order': 'Delivery/Order',
            'delivery / order': 'Delivery/Order',
            'Delivery': 'Delivery/Order',
            'Order Status': 'Delivery/Order'
        }

        df_interactions['issue_category'] = (
            df_interactions['issue_category']
            .astype(str)
            .str.strip()
            .map(issue_category_mapping)
        )

    # 3. Priority to string
    df_interactions['priority'] = df_interactions['priority'].astype(str)


    # Date and time conversion
    df_interactions['created_at'] = pd.to_datetime(
        df_interactions['created_at'],
        format='mixed',
        errors='coerce'
    )

    df_interactions['answered_at'] = pd.to_datetime(
        df_interactions['answered_at'],
        format='mixed',
        errors='coerce'
    )

    df_interactions['ended_at'] = pd.to_datetime(
        df_interactions['ended_at'],
        format='mixed',
        errors='coerce'
    )

    df_interactions['resolved_at'] = pd.to_datetime(
        df_interactions['resolved_at'],
        format='mixed',
        errors='coerce'
    )


    # Agent ID to string
    # Fill missing values BEFORE converting to string
    df_interactions['agent_id'] = df_interactions['agent_id'].fillna(
        df_agents['agent_id'].iloc[0]
    )

    df_interactions['agent_id'] = df_interactions['agent_id'].astype(str)


    # Agent name
    # Fill missing values BEFORE converting to string
    df_interactions['agent_name'] = df_interactions['agent_name'].fillna(
        df_agents['agent_name'].iloc[0]
    )

    df_interactions['agent_name'] = df_interactions['agent_name'].astype(str)


    # Status to string
    df_interactions['status'] = df_interactions['status'].astype(str)


    # Wait time to timedelta
    df_interactions['wait_seconds'] = pd.to_numeric(
        df_interactions['wait_seconds'],
        errors='coerce'
    )

    # Handle if the time is negative, convert to positive
    df_interactions['wait_seconds'] = df_interactions[
        'wait_seconds'
    ].abs()


    # Handling time
    # Convert handle_seconds to numeric
    df_interactions['handle_seconds'] = pd.to_numeric(
        df_interactions['handle_seconds'],
        errors='coerce'
    )

    # If handle_time is null, calculate it from ended_at - created_at
    df_interactions['handle_seconds'] = df_interactions[
        'handle_seconds'
    ].fillna(
        (
            df_interactions['ended_at']
            - df_interactions['created_at']
        ).dt.total_seconds()
    )

    # Handle if the time is negative, convert to positive
    df_interactions['handle_seconds'] = df_interactions[
        'handle_seconds'
    ].abs()


    # First_contact_resolved to string
    df_interactions['first_contact_resolved'] = (
        df_interactions['first_contact_resolved']
        .astype(str)
        .str.strip()
    )


    # First_contact_resolved mapping
    if 'first_contact_resolved' in df_interactions.columns:

        first_contact_resolved_mapping = {
            'Yes': 'Yes',
            'No': 'No',
            'yes': 'Yes',
            'no': 'No',
            'Y': 'Yes',
            'N': 'No',
            '1': 'Yes',
            '0': 'No',
            'true': 'Yes',
            'false': 'No'
        }

        df_interactions['first_contact_resolved'] = (
            df_interactions['first_contact_resolved']
            .map(first_contact_resolved_mapping)
        )

        # If first_contact_resolved is NA,
        # check if contact was resolved within 24 hours
        df_interactions['first_contact_resolved'] = df_interactions.apply(
            lambda row:
            'Yes'
            if pd.notnull(row['resolved_at'])
            and pd.notnull(row['created_at'])
            and (
                row['resolved_at'] - row['created_at']
            ).total_seconds() <= 86400

            else 'No'
            if pd.notnull(row['resolved_at'])
            and pd.notnull(row['created_at'])

            else row['first_contact_resolved'],
            axis=1
        )


    # Escalated to string
    df_interactions['escalated'] = (
        df_interactions['escalated']
        .astype(str)
        .str.strip()
    )


    # Mapping
    if 'escalated' in df_interactions.columns:

        escalated_mapping = {
            'Yes': 'Yes',
            'No': 'No',
            'yes': 'Yes',
            'no': 'No',
            'Y': 'Yes',
            'N': 'No',
            '1': 'Yes',
            '0': 'No',
            'true': 'Yes',
            'false': 'No'
        }

        df_interactions['escalated'] = (
            df_interactions['escalated']
            .map(escalated_mapping)
        )


    # Transferred to string
    df_interactions['transferred'] = (
        df_interactions['transferred']
        .astype(str)
        .str.strip()
    )


    # Mapping
    if 'transferred' in df_interactions.columns:

        transferred_mapping = {
            'Yes': 'Yes',
            'No': 'No',
            'yes': 'Yes',
            'no': 'No',
            'Y': 'Yes',
            'N': 'No',
            '1': 'Yes',
            '0': 'No',
            'true': 'Yes',
            'false': 'No'
        }

        df_interactions['transferred'] = (
            df_interactions['transferred']
            .map(transferred_mapping)
        )


    # Updated_at to datetime
    df_interactions['updated_at'] = pd.to_datetime(
        df_interactions['updated_at'],
        format='mixed',
        errors='coerce'
    )


    # Save cleaned data
    df_interactions.to_csv(
        'cleaned_interactions_data.csv',
        index=False
    )

    print(
        "Cleaned Interactions Data saved to "
        "cleaned_interactions_data.csv"
    )


# Run the function
clean_interactions_data(
    df_interactions_2,
    df_agents_2
)


# Cleaning QAS Data
# Cleaning Surveys Data
# Cleaning Shifts Data
# Cleaning Customers Data